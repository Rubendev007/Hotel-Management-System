from datetime import date, timedelta
from io import StringIO
from smtplib import SMTPException
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.contrib.messages import get_messages
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse

from accounts.models import Guest
from .forms import editBooking
from .models import Booking, Room, Season


class BookingStabilizationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="guest", password="test-password")
        self.guest = Guest.objects.create(user=self.user, phoneNumber="+12025550101")
        self.room = Room.objects.create(
            number=101, capacity=2, numberOfBeds=1, roomType="Normal", price=100)
        self.client.force_login(self.user)

    def make_booking(self):
        return Booking.objects.create(
            guest=self.guest, roomNumber=self.room,
            startDate=date(2026, 10, 1), endDate=date(2026, 10, 3))

    def set_pending(self, booking):
        session = self.client.session
        session["booking_id"] = booking.pk
        session["payment_code"] = "expected-code"
        session.save()

    def test_booking_get_redirects_with_warning(self):
        response = self.client.get(reverse("booking-make"))
        self.assertRedirects(response, reverse("rooms"), fetch_redirect_response=False)
        self.assertTrue(list(get_messages(response.wsgi_request)))
        self.assertFalse(Booking.objects.exists())

    def test_booking_missing_fields_redirects_with_warning(self):
        valid = {"roomid": self.room.pk, "fd": "2026-10-01", "ld": "2026-10-03"}
        for field in valid:
            for value in (None, ""):
                data = valid.copy()
                if value is None:
                    del data[field]
                else:
                    data[field] = value
                with self.subTest(field=field, value=value):
                    response = self.client.post(reverse("booking-make"), data)
                    self.assertRedirects(response, reverse("rooms"), fetch_redirect_response=False)
                    self.assertTrue(list(get_messages(response.wsgi_request)))
        self.assertFalse(Booking.objects.exists())

    @patch("room.views.render", return_value=HttpResponse())
    def test_rooms_without_group_uses_guest_role(self, render):
        self.client.get(reverse("rooms"))
        self.assertEqual(render.call_args.args[1], "guest/rooms.html")
        self.assertEqual(render.call_args.args[2]["role"], "guest")

    def test_my_room_without_active_booking_shows_booking_notice(self):
        today = date.today()
        Booking.objects.create(
            guest=self.guest, roomNumber=self.room,
            startDate=today - timedelta(days=3),
            endDate=today - timedelta(days=1),
        )

        response = self.client.get(reverse("my-room"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["current_booking"])
        self.assertContains(
            response,
            "No room booked currently. Please book a room first to see details.",
        )

    def test_my_room_shows_active_booking(self):
        today = date.today()
        booking = Booking.objects.create(
            guest=self.guest, roomNumber=self.room,
            startDate=today, endDate=today + timedelta(days=1),
        )

        response = self.client.get(reverse("my-room"))

        self.assertEqual(response.context["current_booking"], booking)
        self.assertContains(response, "Room 101")

    def test_guest_dashboard_counts_only_past_guest_bookings(self):
        today = date.today()
        Booking.objects.create(
            guest=self.guest, roomNumber=self.room,
            startDate=today - timedelta(days=3),
            endDate=today - timedelta(days=1),
        )
        active_booking = Booking.objects.create(
            guest=self.guest, roomNumber=self.room,
            startDate=today, endDate=today + timedelta(days=1),
        )

        response = self.client.get(reverse("guest-dashboard"))

        self.assertEqual(response.context["past_count"], 1)
        self.assertEqual(response.context["active"], active_booking)

    def test_admin_room_sidebar_uses_admin_dashboard_and_employee_profile(self):
        self.user.groups.add(Group.objects.create(name="admin"))

        response = self.client.get(reverse("rooms"))

        self.assertContains(response, f'href="{reverse("admin_dashboard")}"')
        self.assertContains(
            response,
            f'href="{reverse("employee-profile", args=[self.user.pk])}"',
        )
        self.assertContains(response, f'href="{reverse("logout")}"', count=1)
        self.assertContains(response, "Profile", count=1)
        self.assertNotContains(response, "Options")
        self.assertNotContains(response, f'href="{reverse("guest-profile", args=[self.user.pk])}"')

    def test_admin_guest_dashboard_url_redirects_to_admin_dashboard(self):
        self.user.groups.add(Group.objects.create(name="admin"))

        response = self.client.get(reverse("guest-dashboard"))

        self.assertRedirects(
            response,
            reverse("admin_dashboard"),
            fetch_redirect_response=False,
        )

    def test_admin_can_create_seasonal_pricing_period(self):
        self.user.groups.add(Group.objects.create(name="admin"))
        start_date = date.today() + timedelta(days=2)
        end_date = start_date + timedelta(days=3)

        response = self.client.post(reverse("season-create"), {
            "name": "Test Season",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "markup_percentage": "15.00",
            "is_active": "on",
        })

        self.assertRedirects(
            response,
            reverse("seasons"),
            fetch_redirect_response=False,
        )
        season = Season.objects.get(name="Test Season")
        self.assertEqual(season.markup_percentage, 15)
        self.assertTrue(season.is_active)

    def test_admin_season_form_rejects_end_before_start(self):
        self.user.groups.add(Group.objects.create(name="admin"))
        start_date = date.today() + timedelta(days=5)

        response = self.client.post(reverse("season-create"), {
            "name": "Invalid Season",
            "start_date": start_date.isoformat(),
            "end_date": (start_date - timedelta(days=1)).isoformat(),
            "markup_percentage": "15.00",
            "is_active": "on",
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Season.objects.filter(name="Invalid Season").exists())
        self.assertContains(response, "End date must be on or after the start date.")

    def test_admin_can_create_off_season_discount(self):
        self.user.groups.add(Group.objects.create(name="admin"))
        start_date = date.today() + timedelta(days=2)

        response = self.client.post(reverse("season-create"), {
            "name": "Quiet Season",
            "start_date": start_date.isoformat(),
            "end_date": (start_date + timedelta(days=10)).isoformat(),
            "markup_percentage": "-20",
            "is_active": "on",
        })

        self.assertRedirects(response, reverse("seasons"), fetch_redirect_response=False)
        self.assertEqual(Season.objects.get(name="Quiet Season").markup_percentage, -20)

    def test_admin_cannot_create_discount_below_one_hundred_percent(self):
        self.user.groups.add(Group.objects.create(name="admin"))
        start_date = date.today() + timedelta(days=2)

        response = self.client.post(reverse("season-create"), {
            "name": "Invalid Discount",
            "start_date": start_date.isoformat(),
            "end_date": (start_date + timedelta(days=10)).isoformat(),
            "markup_percentage": "-100.01",
            "is_active": "on",
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Season.objects.filter(name="Invalid Discount").exists())
        self.assertContains(response, "Markup cannot be lower than -100%.")

    def test_admin_can_edit_disable_and_delete_season(self):
        self.user.groups.add(Group.objects.create(name="admin"))
        season = Season.objects.create(
            name="Existing Season",
            start_date=date.today() + timedelta(days=2),
            end_date=date.today() + timedelta(days=5),
            markup_percentage=12,
        )

        edit_response = self.client.post(reverse("season-edit", args=[season.pk]), {
            "name": "Updated Season",
            "start_date": season.start_date.isoformat(),
            "end_date": season.end_date.isoformat(),
            "markup_percentage": "18.50",
            "is_active": "on",
        })
        self.assertRedirects(edit_response, reverse("seasons"), fetch_redirect_response=False)
        season.refresh_from_db()
        self.assertEqual(season.name, "Updated Season")
        self.assertEqual(season.markup_percentage, 18.5)

        toggle_response = self.client.post(reverse("season-toggle", args=[season.pk]))
        self.assertRedirects(toggle_response, reverse("seasons"), fetch_redirect_response=False)
        season.refresh_from_db()
        self.assertFalse(season.is_active)

        delete_response = self.client.post(reverse("season-delete", args=[season.pk]))
        self.assertRedirects(delete_response, reverse("seasons"), fetch_redirect_response=False)
        self.assertFalse(Season.objects.filter(pk=season.pk).exists())

    def test_non_admin_cannot_access_season_management(self):
        response = self.client.get(reverse("seasons"))

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_booking_total_applies_active_season_markup(self):
        start_date = date.today() + timedelta(days=2)
        end_date = start_date + timedelta(days=2)
        Season.objects.create(
            name="Test Markup",
            start_date=start_date,
            end_date=end_date - timedelta(days=1),
            markup_percentage=10,
            is_active=True,
        )

        response = self.client.post(reverse("booking-make"), {
            "roomid": self.room.pk,
            "fd": start_date.isoformat(),
            "ld": end_date.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(response.context["total"], 220)

    def test_guest_room_catalog_shows_off_season_discount(self):
        today = date.today()
        Season.objects.create(
            name="Current Off Season",
            start_date=today,
            end_date=today + timedelta(days=5),
            markup_percentage=-20,
            is_active=True,
        )

        response = self.client.get(reverse("rooms"))

        room = response.context["rooms"][0]
        self.assertEqual(room.seasonal_markup, -20)
        self.assertEqual(room.seasonal_price, 80)
        self.assertContains(response, "Save 20.0%")
        self.assertContains(response, "price-original")
        self.assertContains(response, "Rs. 80.00")

    def test_guest_room_catalog_discloses_peak_season_increase(self):
        today = date.today()
        Season.objects.create(
            name="Current Peak Season",
            start_date=today,
            end_date=today + timedelta(days=5),
            markup_percentage=25,
            is_active=True,
        )

        response = self.client.get(reverse("rooms"))

        self.assertContains(response, "Peak season +25.0%")
        self.assertContains(response, "price-original")
        self.assertContains(response, "Rs. 125.00")

    def test_room_catalog_prices_by_selected_checkin_date(self):
        start_date = date.today() + timedelta(days=4)
        Season.objects.create(
            name="Future Off Season",
            start_date=start_date,
            end_date=start_date + timedelta(days=3),
            markup_percentage=-15,
            is_active=True,
        )

        response = self.client.post(reverse("rooms"), {
            "dateFilter": "",
            "fd": start_date.isoformat(),
            "ld": (start_date + timedelta(days=1)).isoformat(),
        })

        self.assertEqual(response.context["rooms"][0].seasonal_markup, -15)
        self.assertContains(response, "Save 15.0%")

    def test_booking_summary_shows_discounted_nightly_rates(self):
        start_date = date.today() + timedelta(days=2)
        end_date = start_date + timedelta(days=2)
        Season.objects.create(
            name="Off Season",
            start_date=start_date,
            end_date=end_date - timedelta(days=1),
            markup_percentage=-20,
            is_active=True,
        )

        response = self.client.post(reverse("booking-make"), {
            "roomid": self.room.pk,
            "fd": start_date.isoformat(),
            "ld": end_date.isoformat(),
        })

        self.assertEqual(response.context["total"], 160)
        self.assertEqual(response.context["base_total"], 200)
        self.assertEqual([night["rate"] for night in response.context["nightly_prices"]], [80, 80])
        self.assertContains(response, "Off-season")
        self.assertContains(response, "Rs. 160.00")

    def test_booking_make_rejects_past_checkin_and_invalid_checkout(self):
        today = date.today()
        for check_in, check_out in (
            (today - timedelta(days=1), today + timedelta(days=1)),
            (today, today),
        ):
            with self.subTest(check_in=check_in, check_out=check_out):
                response = self.client.post(reverse("booking-make"), {
                    "roomid": self.room.pk,
                    "fd": check_in.isoformat(),
                    "ld": check_out.isoformat(),
                })
                self.assertRedirects(
                    response, reverse("rooms"), fetch_redirect_response=False)
        self.assertFalse(Booking.objects.exists())

    def test_booking_make_rejects_overlapping_booking(self):
        today = date.today()
        Booking.objects.create(
            guest=self.guest,
            roomNumber=self.room,
            startDate=today + timedelta(days=2),
            endDate=today + timedelta(days=4),
        )
        response = self.client.post(reverse("booking-make"), {
            "roomid": self.room.pk,
            "fd": (today + timedelta(days=4)).isoformat(),
            "ld": (today + timedelta(days=6)).isoformat(),
            "bookGuestButton": "",
            "name1": "",
        })

        self.assertRedirects(
            response, reverse("rooms"), fetch_redirect_response=False)
        self.assertEqual(Booking.objects.count(), 1)

    def test_receptionist_express_checkin_rejects_overlapping_booking(self):
        self.user.groups.add(Group.objects.create(name="receptionist"))
        today = date.today()
        Booking.objects.create(
            guest=self.guest,
            roomNumber=self.room,
            startDate=today + timedelta(days=1),
            endDate=today + timedelta(days=3),
        )

        response = self.client.post(reverse("rooms"), {
            "guest_name": "Another Guest",
            "room_number": self.room.number,
            "check_in": (today + timedelta(days=3)).isoformat(),
            "check_out": (today + timedelta(days=5)).isoformat(),
        })

        self.assertRedirects(
            response, reverse("rooms"), fetch_redirect_response=False)
        self.assertEqual(Booking.objects.count(), 1)

    def test_receptionist_room_grid_marks_current_room_unavailable(self):
        self.user.groups.add(Group.objects.create(name="receptionist"))
        today = date.today()
        Booking.objects.create(
            guest=self.guest,
            roomNumber=self.room,
            startDate=today,
            endDate=today + timedelta(days=1),
        )

        response = self.client.get(reverse("rooms"))

        self.assertTrue(response.context["rooms"][0].is_unavailable)

    def test_guest_room_catalog_blocks_rooms_being_cleaned(self):
        self.room.status = "cleaning"
        self.room.save(update_fields=["status"])

        response = self.client.get(reverse("rooms"))

        self.assertTrue(response.context["rooms"][0].is_unavailable)
        self.assertContains(response, "Occupied / Unavailable")
        self.assertNotContains(response, "Book room")

    def test_guest_room_catalog_blocks_dirty_rooms(self):
        self.room.status = "dirty"
        self.room.save(update_fields=["status"])

        response = self.client.get(reverse("rooms"))

        self.assertTrue(response.context["rooms"][0].is_unavailable)
        self.assertContains(response, "Occupied / Unavailable")

    def test_availability_date_filter_excludes_rooms_being_cleaned(self):
        self.room.status = "cleaning"
        self.room.save(update_fields=["status"])

        response = self.client.post(reverse("rooms"), {
            "dateFilter": "",
            "fd": date.today().isoformat(),
            "ld": (date.today() + timedelta(days=1)).isoformat(),
        })

        self.assertEqual(response.context["rooms"], [])

    def test_guest_room_detail_disables_booking_while_cleaning(self):
        self.room.status = "cleaning"
        self.room.save(update_fields=["status"])

        response = self.client.get(reverse("room-detail", args=[self.room.number]))

        self.assertFalse(response.context["is_available"])
        self.assertTrue(response.context["is_cleaning"])
        self.assertContains(response, "This room is being cleaned")
        self.assertNotContains(response, "Book This Room")

    def test_booking_submission_rejects_rooms_being_cleaned(self):
        self.room.status = "cleaning"
        self.room.save(update_fields=["status"])
        check_in = date.today() + timedelta(days=1)

        response = self.client.post(reverse("booking-make"), {
            "roomid": self.room.pk,
            "fd": check_in.isoformat(),
            "ld": (check_in + timedelta(days=2)).isoformat(),
            "bookGuestButton": "",
            "name1": "",
        })

        self.assertRedirects(response, reverse("rooms"), fetch_redirect_response=False)
        self.assertFalse(Booking.objects.exists())
        self.assertNotIn("booking_id", self.client.session)

    def test_marking_cleaned_restores_room_availability(self):
        self.user.groups.add(Group.objects.create(name="receptionist"))
        self.room.status = "cleaning"
        self.room.save(update_fields=["status"])

        response = self.client.get(reverse("mark-cleaned", args=[self.room.number]))

        self.assertRedirects(response, reverse("rooms"), fetch_redirect_response=False)
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, "available")

        catalog_response = self.client.get(reverse("rooms"))
        self.assertFalse(catalog_response.context["rooms"][0].is_unavailable)

    def test_edit_booking_form_validates_booking_dates(self):
        today = date.today()
        for check_in, check_out in (
            (today - timedelta(days=1), today + timedelta(days=1)),
            (today, today),
        ):
            with self.subTest(check_in=check_in, check_out=check_out):
                form = editBooking(data={
                    "startDate": check_in.isoformat(),
                    "endDate": check_out.isoformat(),
                })
                self.assertFalse(form.is_valid())

    def test_home_without_group_redirects_to_guest_profile(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("guest-profile", args=[self.user.pk]),
                             fetch_redirect_response=False)

    @patch("accounts.views.render", return_value=HttpResponse())
    def test_guest_profile_without_group_uses_guest_role(self, render):
        self.client.get(reverse("guest-profile", args=[self.user.pk]))
        self.assertEqual(render.call_args.args[2]["role"], "guest")

    def test_guest_booking_helpers(self):
        self.assertEqual(self.guest.numOfBooking(), 0)
        self.assertEqual(self.guest.numOfDays(), 0)
        self.assertEqual(self.guest.numOfLastBookingDays(), 0)
        self.assertIsNone(self.guest.currentRoom())
        self.make_booking()
        self.assertEqual(self.guest.numOfBooking(), 1)
        self.assertEqual(self.guest.numOfDays(), 2)
        self.assertEqual(self.guest.numOfLastBookingDays(), 2)
        self.assertEqual(self.guest.currentRoom(), self.room)

    def test_creation_stores_booking_in_session(self):
        check_in = date.today() + timedelta(days=1)
        check_out = check_in + timedelta(days=2)
        response = self.client.post(reverse("booking-make"), {
            "roomid": self.room.pk,
            "fd": check_in.isoformat(),
            "ld": check_out.isoformat(),
            "bookGuestButton": "", "name1": ""})
        self.assertRedirects(response, reverse("payment"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["booking_id"], Booking.objects.get().pk)

    def test_failed_verification_deletes_only_session_booking(self):
        pending = self.make_booking()
        unrelated = self.make_booking()
        self.set_pending(pending)
        response = self.client.post(reverse("verify"), {
            "verify": "", "realCode": "incorrect", "tempCode": "expected-code"})
        self.assertRedirects(response, reverse("rooms"), fetch_redirect_response=False)
        self.assertFalse(Booking.objects.filter(pk=pending.pk).exists())
        self.assertTrue(Booking.objects.filter(pk=unrelated.pk).exists())
        self.assertNotIn("booking_id", self.client.session)
        self.assertNotIn("payment_code", self.client.session)

    def test_session_without_pending_booking_cannot_delete_booking(self):
        booking = self.make_booking()
        response = self.client.post(reverse("verify"), {
            "verify": "", "realCode": "incorrect", "tempCode": "expected-code"})
        self.assertRedirects(response, reverse("rooms"), fetch_redirect_response=False)
        self.assertTrue(Booking.objects.filter(pk=booking.pk).exists())

    def test_verify_get_without_pending_booking_redirects(self):
        response = self.client.get(reverse("verify"))
        self.assertRedirects(response, reverse("rooms"), fetch_redirect_response=False)

    @patch("hotel.views.render", return_value=HttpResponse())
    @patch("hotel.views.send_mail")
    def test_receptionist_payment_uses_session_booking_guest(self, send_mail, render):
        self.user.groups.add(Group.objects.create(name="receptionist"))
        pending = self.make_booking()
        other_user = User.objects.create_user(username="other", email="other@example.com")
        other_guest = Guest.objects.create(user=other_user, phoneNumber="+12025550102")
        Booking.objects.create(guest=other_guest, roomNumber=self.room,
                               startDate=date(2026, 11, 1), endDate=date(2026, 11, 3))
        self.user.email = "pending@example.com"
        self.user.save()
        self.set_pending(pending)
        self.client.get(reverse("payment"))
        self.assertEqual(send_mail.call_args.args[3], ["pending@example.com"])

    @patch("hotel.views.render", return_value=HttpResponse())
    def test_email_errors_keep_verification_working(self, render):
        for error in (ConnectionRefusedError(), SMTPException(), OSError()):
            with self.subTest(error=type(error).__name__):
                pending = self.make_booking()
                self.set_pending(pending)
                with self.settings(DEBUG=True), patch("hotel.views.send_mail", side_effect=error), \
                        patch("sys.stdout", new_callable=StringIO) as output:
                    response = self.client.get(reverse("payment"))
                self.assertEqual(response.status_code, 200)
                code = self.client.session["payment_code"]
                self.assertIn(code, output.getvalue())
                self.assertIn(
                    "Failed to send email verification. Code printed to terminal.",
                    [str(message) for message in get_messages(response.wsgi_request)])
                self.assertEqual(self.client.get(reverse("verify")).status_code, 200)
                response = self.client.post(reverse("verify"), {"verify": "", "realCode": code})
                self.assertRedirects(response, reverse("rooms"), fetch_redirect_response=False)
                self.assertTrue(Booking.objects.filter(pk=pending.pk).exists())
                self.assertNotIn("booking_id", self.client.session)

    @patch("hotel.views.render", return_value=HttpResponse())
    def test_console_backend_prints_verification_email(self, render):
        self.user.email = "guest@example.com"
        self.user.save()
        self.set_pending(self.make_booking())
        with self.settings(DEBUG=True, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"), \
                patch("sys.stdout", new_callable=StringIO) as output:
            response = self.client.get(reverse("payment"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.client.session["payment_code"], output.getvalue())
        self.assertIn("guest@example.com", output.getvalue())

    @patch("hotel.views.render", return_value=HttpResponse())
    @patch("hotel.views.send_mail", side_effect=ConnectionRefusedError())
    def test_production_email_failure_does_not_print_code(self, send_mail, render):
        self.set_pending(self.make_booking())
        with self.settings(DEBUG=False), patch("sys.stdout", new_callable=StringIO) as output:
            response = self.client.get(reverse("payment"))
        self.assertEqual(response.status_code, 200)
        code = self.client.session["payment_code"]
        self.assertNotIn(code, output.getvalue())
        self.assertNotIn(code, str(render.call_args.args[2]))
        self.assertNotIn(code, " ".join(str(message) for message in get_messages(response.wsgi_request)))

    def test_successful_verification_clears_session_and_keeps_booking(self):
        pending = self.make_booking()
        self.set_pending(pending)
        response = self.client.post(reverse("verify"), {
            "verify": "", "realCode": "expected-code", "tempCode": "expected-code"})
        self.assertRedirects(response, reverse("rooms"), fetch_redirect_response=False)
        self.assertTrue(Booking.objects.filter(pk=pending.pk).exists())
        self.assertNotIn("booking_id", self.client.session)
        self.assertNotIn("payment_code", self.client.session)
