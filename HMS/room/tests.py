from datetime import date
from io import StringIO
from smtplib import SMTPException
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.contrib.messages import get_messages
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse

from accounts.models import Guest
from .models import Booking, Room


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
        response = self.client.post(reverse("booking-make"), {
            "roomid": self.room.pk, "fd": "2026-10-01", "ld": "2026-10-03",
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
