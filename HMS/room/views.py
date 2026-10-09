# imports
from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm

from django.db.models import Q, Count
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import Group, User
from django.http import HttpResponse

from django.utils import timezone
from datetime import datetime, date, timedelta
import random
import re
# Create your views here.
from accounts.models import *
from room.models import *
from hotel.models import *
from .forms import *
from housekeeping_utils import rebalance_cleaning_tasks


def room_unavailable_for_dates(room, check_in, check_out):
    if (room.status or '').strip().lower() in ('occupied', 'dirty', 'cleaning'):
        return True
    if (
        room.statusStartDate
        and room.statusEndDate
        and room.statusStartDate <= check_out
        and room.statusEndDate >= check_in
    ):
        return True
    return Booking.objects.filter(
        roomNumber=room,
        endDate__gte=check_in,
        startDate__lte=check_out,
    ).exists()


def seasonal_markup_for_date(check_date):
    active_seasons = Season.objects.filter(
        is_active=True,
        start_date__lte=check_date,
        end_date__gte=check_date,
    )
    return max(
        (float(season.markup_percentage) for season in active_seasons),
        default=0.0,
    )


def apply_seasonal_rates(rooms, pricing_date):
    markup = seasonal_markup_for_date(pricing_date)
    for room in rooms:
        room.seasonal_markup = markup
        room.seasonal_price = round(float(room.price) * (1 + markup / 100), 2)
    return rooms



def csrf_failure(request, reason=""):
    messages.error(request, "Your session expired or changed. Please try logging in again.")
    return redirect('login')


@ login_required(login_url='login')
def rooms(request):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    path = role + "/"
    # Housekeeping uses staff template since no housekeeping/rooms.html exists
    if role == 'housekeeping':
        path = 'staff/'
    rooms = Room.objects.all()
    firstDayStr = None
    lastDateStr = None
    pricing_date = date.today()

    def chech_availability(fd, ed):
        check_in = fd.date()
        check_out = ed.date()
        return [
            room for room in rooms
            if not room_unavailable_for_dates(room, check_in, check_out)
        ]

    if request.method == "POST":
        if "guest_name" in request.POST:
            # Express Check-In
            room_number = request.POST.get("room_number")
            guest_name = request.POST.get("guest_name", "").strip()
            guest_email = request.POST.get("guest_email", "").strip()
            guest_phone = request.POST.get("guest_phone", "").strip()

            # Validate room exists
            try:
                room = Room.objects.get(number=room_number)
            except (Room.DoesNotExist, TypeError, ValueError):
                messages.error(request, "Please select a valid room.")
                return redirect("rooms")

            today = date.today()
            try:
                sd = datetime.strptime(request.POST.get("check_in", str(today)), '%Y-%m-%d').date()
                ed = datetime.strptime(request.POST.get("check_out", str(today + timedelta(days=1))), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                messages.error(request, "Please enter valid check-in and check-out dates.")
                return redirect("rooms")
            if sd < today:
                messages.error(request, "Check-in date cannot be in the past.")
                return redirect("rooms")
            if ed <= sd:
                messages.error(request, "Check-out date must be after check-in date.")
                return redirect("rooms")
            if room_unavailable_for_dates(room, sd, ed):
                messages.error(request, "This room is already booked/occupied for the selected dates.")
                return redirect("rooms")

            # Get or create Guest profile
            guest = None
            if guest_email:
                user = User.objects.filter(email=guest_email).first()
                if user:
                    guest = Guest.objects.filter(user=user).first()
            if not guest and guest_name:
                user = User.objects.filter(username=guest_name).first()
                if user:
                    guest = Guest.objects.filter(user=user).first()
            if not guest:
                username_slug = guest_name.lower().replace(" ", "_")
                user, created = User.objects.get_or_create(
                    username=username_slug,
                    defaults={'first_name': guest_name, 'email': guest_email}
                )
                if not created and not user.email and guest_email:
                    user.email = guest_email
                    user.save(update_fields=['email'])
                if not user.first_name:
                    user.first_name = guest_name
                    user.save(update_fields=['first_name'])
                guest = Guest.objects.filter(user=user).first()
                if not guest:
                    guest = Guest.objects.create(user=user, phoneNumber=guest_phone or "+0000000000")

            room.statusStartDate = sd
            room.statusEndDate = ed
            room.save()
            Booking.objects.create(roomNumber=room, guest=guest, startDate=sd, endDate=ed, total_price=room.price or 0)
            messages.success(request, f"Checked in {guest_name} to Room {room.number}.")
            return redirect("rooms")

        if "dateFilter" in request.POST:
            firstDayStr = request.POST.get("fd", "")
            lastDateStr = request.POST.get("ld", "")

            try:
                firstDay = datetime.strptime(firstDayStr, '%Y-%m-%d')
                lastDate = datetime.strptime(lastDateStr, '%Y-%m-%d')
            except (ValueError, TypeError):
                messages.error(request, "Please select valid availability dates.")
                return redirect("rooms")
            if lastDate.date() < firstDay.date():
                messages.error(request, "The end date must be on or after the start date.")
                return redirect("rooms")

            pricing_date = firstDay.date()
            rooms = chech_availability(firstDay, lastDate)

        if "filter" in request.POST:
            if (request.POST.get("number") != ""):
                rooms = rooms.filter(
                    number__contains=request.POST.get("number"))

            if (request.POST.get("capacity") != ""):
                rooms = rooms.filter(
                    capacity__gte=request.POST.get("capacity"))

            if (request.POST.get("nob") != ""):
                rooms = rooms.filter(
                    numberOfBeds__gte=request.POST.get("nob"))

            if (request.POST.get("type") != ""):
                rooms = rooms.filter(
                    roomType__contains=request.POST.get("type"))

            if (request.POST.get("price") != ""):
                rooms = rooms.filter(
                    price__lte=request.POST.get("price"))

            rooms = apply_seasonal_rates(rooms, pricing_date)
            context = {
                "role": role,
                "rooms": rooms,
                "fd": firstDayStr,
                "ld": lastDateStr,
                "pricing_date": pricing_date,
                "number": request.POST.get("number"),
                "capacity": request.POST.get("capacity"),
                "nob": request.POST.get("nob"),
                "price": request.POST.get("price"),
                "type": request.POST.get("type")
            }
            return render(request, path + "rooms.html", context)

    from datetime import date as dt
    today = dt.today()
    if firstDayStr:
        pricing_date = datetime.strptime(firstDayStr, '%Y-%m-%d').date()
    active_booking_ids = list(Booking.objects.filter(
        startDate__lte=today,
        endDate__gte=today,
    ).values_list('roomNumber_id', flat=True))
    unavailable_room_ids = set(active_booking_ids)
    unavailable_room_ids.update(
        Room.objects.filter(
            status__in=['occupied', 'dirty', 'cleaning']
        ).values_list('number', flat=True)
    )
    unavailable_room_ids.update(
        Room.objects.filter(
            statusStartDate__lte=today,
            statusEndDate__gte=today,
        ).values_list('number', flat=True)
    )
    for room in rooms:
        room.is_unavailable = room.number in unavailable_room_ids
    rooms = apply_seasonal_rates(rooms, pricing_date)
    context = {
        "role": role,
        'rooms': rooms,
        'fd': firstDayStr,
        'ld': lastDateStr,
        'today': today,
        'pricing_date': pricing_date,
        'tomorrow': today + __import__('datetime').timedelta(days=1),
        'active_booking_ids': active_booking_ids,
        'unavailable_room_ids': unavailable_room_ids,
    }
    return render(request, path + "rooms.html", context)


@login_required(login_url='login')
def add_room(request):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    path = role + "/"

    if request.method == "POST":
        guest = None
        if role == 'guest':
            guest = request.user.guest
        elif role == 'manager' or role == 'admin' or role == 'receptionist':
            guest = request.user.employee

        # announcement = Announcement(sender = sender, content = request.POST.get('textid'))
        number = request.POST.get('number')
        capacity = request.POST.get('capacity')
        numberOfBeds = request.POST.get('beds')
        roomType = request.POST.get('roomType')
        price = request.POST.get('price')
        print(capacity)
        room = Room(number=number, capacity=capacity,
                    numberOfBeds=numberOfBeds, roomType=roomType, price=price,
                    image=request.FILES.get('image'))

        room.save()
        return redirect('rooms')

    context = {
        "role": role
    }
    return render(request, path + "add-room.html", context)


@login_required(login_url='login')
def room_profile(request, id):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    path = role + "/"
    tempRoom = Room.objects.get(number=id)
    bookings = Booking.objects.filter(roomNumber=tempRoom)
    guests = Guest.objects.all()
    bookings2 = Booking.objects.all()
    context = {
        "role": role,
        "bookings": bookings,
        "room": tempRoom,
        "guests": guests,
        "bookings2": bookings2,
        "today": date.today(),
    }

    if request.method == "POST":
        if "lockRoom" in request.POST:
            fd = request.POST.get("bsd")
            ed = request.POST.get("bed")
            fd = datetime.strptime(fd, '%Y-%m-%d')
            ed = datetime.strptime(ed, '%Y-%m-%d')
            check = True
            for b in bookings:
                if b.endDate >= fd.date() and b.startDate <= ed.date():
                    check = False
                    break
            if check:
                tempRoom.statusStartDate = fd
                tempRoom.statusEndDate = ed
                tempRoom.save()
            else:
                messages.error(request, "There is a booking in the interval!")
        if "unlockRoom" in request.POST:
            tempRoom.statusStartDate = None
            tempRoom.statusEndDate = None
            tempRoom.save()
        if "deleteRoom" in request.POST:
            check = True
            for b in bookings:
                if b.startDate <= datetime.now().date() or b.endDate >= datetime.now().date():
                    check = False
            if check:
                tempRoom.delete()
                return redirect("rooms")
            else:
                messages.error(request, "There is a booking in the interval!")

    return render(request, path + "room-profile.html", context)


@login_required(login_url='login')
def room_edit(request, pk):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    path = role + "/"

    room = Room.objects.get(number=pk)
    form1 = editRoom(instance=room)

    context = {
        "role": role,
        "room": room,
        "form1": form1
    }

    if request.method == 'POST':
        form1 = editRoom(request.POST, request.FILES, instance=room)
        if form1.is_valid():
            instance = form1.save(commit=False)
            if request.FILES.get('image'):
                instance.image = request.FILES.get('image')
            instance.save()
            return redirect('rooms')
    return render(request, path + "room-edit.html", context)


@login_required(login_url='login')
def room_detail(request, pk):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    path = role + "/"

    room = Room.objects.get(number=pk)
    amenities = {
        'King': ['King-size Bed', 'Premium Linens', 'Mini Bar', 'Work Desk', 'Smart TV', 'Air Conditioning'],
        'Luxury': ['King-size Bed', 'Jacuzzi', 'Mini Bar', 'Work Desk', 'Smart TV', 'Air Conditioning', 'Room Service', 'Premium Toiletries'],
        'Normal': ['Double Bed', 'Basic Amenities', 'TV', 'Air Conditioning', 'Wi-Fi', 'Coffee Maker'],
        'Economic': ['Single Bed', 'Shared Bathroom', 'Wi-Fi', 'Basic Amenities'],
    }
    room_amenities = amenities.get(room.roomType, [])

    # Dynamic status evaluator based on active Booking
    today = timezone.now().date()
    has_active = Booking.objects.filter(
        roomNumber=room, startDate__lte=today, endDate__gte=today
    ).exists()

    # Overlap validation for new bookings (used when posting from room-detail)
    if request.method == "POST" and ("book" in request.POST or "fd" in request.POST):
        # Hard block: reject booking if room currently occupied
        if has_active:
            messages.error(request, "This room is currently occupied. Please check out the current guest first before booking.")
            return redirect("room-detail", pk=pk)
        try:
            sd = datetime.strptime(request.POST.get("fd", str(today)), "%Y-%m-%d").date()
            ed = datetime.strptime(request.POST.get("ld", str(today + timedelta(days=2))), "%Y-%m-%d").date()
            if sd < today:
                messages.error(request, "Check-in date cannot be in the past.")
                return redirect("room-detail", pk=pk)
            if ed <= sd:
                messages.error(request, "Check-out date must be after check-in date.")
                return redirect("room-detail", pk=pk)
            if room_unavailable_for_dates(room, sd, ed):
                messages.error(request, "This room is already booked/occupied for the selected dates.")
                return redirect("room-detail", pk=pk)
        except (ValueError, TypeError):
            messages.error(request, "Please enter valid check-in and check-out dates.")
            return redirect("room-detail", pk=pk)

    is_occupied = has_active
    is_available = not room_unavailable_for_dates(room, today, today)
    fd = request.GET.get('fd') or str(today)
    ld = request.GET.get('ld') or str(today + timedelta(days=2))
    try:
        pricing_date = datetime.strptime(fd, "%Y-%m-%d").date()
    except ValueError:
        pricing_date = today
    seasonal_markup = seasonal_markup_for_date(pricing_date)

    context = {
        "role": role,
        "room": room,
        "amenities": room_amenities,
        "is_available": is_available,
        "is_occupied": is_occupied,
        "is_cleaning": (room.status or '').strip().lower() in ('dirty', 'cleaning'),
        "pricing_date": pricing_date,
        "seasonal_markup": seasonal_markup,
        "seasonal_price": round(float(room.price) * (1 + seasonal_markup / 100), 2),
        "fd": fd,
        "ld": ld,
    }
    return render(request, path + "room-detail.html", context)


@login_required(login_url='login')
def my_room(request):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    if role != 'guest':
        return redirect('rooms')

    guest = Guest.objects.filter(user=request.user).first()
    today = date.today()
    current_booking = None
    if guest:
        current_booking = Booking.objects.filter(
            guest=guest,
            endDate__gte=today,
        ).select_related('roomNumber').order_by('-startDate').first()

    context = {
        'role': role,
        'current_booking': current_booking,
        'today': today,
    }
    return render(request, 'guest/my-room.html', context)


@ login_required(login_url='login')
def room_services(request):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    path = role + "/"

    room_services = RoomServices.objects.all()
    context = {
        "role": role,
        "room_services": room_services
    }
    return render(request, path + "room-services.html", context)


@login_required(login_url='login')
def current_room_services(request):
    import datetime

    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    path = role + "/"

    curGuest = Guest.objects.get(user=request.user)
    curBooking = Booking.objects.filter(guest=curGuest).last()
    if curBooking is not None:
        curRoom = Room.objects.get(number=curBooking.roomNumber.number)
    else:
        context = {
            "role": role,
            "error": "You Don't Have Booking Right Now"
        }
        return render(request, path + "current-room-services.html", context)
    curRoomServices = RoomServices.objects.filter(curBooking=curBooking)
    # Clean up orphaned service requests without matching tasks
    for svc in curRoomServices:
        has_task = Task.objects.filter(room=svc.room, description__icontains=svc.servicesType).exists() or \
                   Task.objects.filter(employee__user__groups__name='staff', description__icontains=svc.servicesType).exists()
        if not has_task:
            try:
                svc.delete()
            except Exception:
                pass

    room_services = RoomServices.objects.all()

    staff_group = Group.objects.filter(name='staff').first()
    staff_users = User.objects.filter(groups=staff_group) if staff_group else User.objects.none()
    allEmployees = list(Employee.objects.filter(user__in=staff_users))
    availableEmployee = list()
    maxTaskNum = 10

    for e in allEmployees:
        counter = 0
        empTasks = Task.objects.filter(employee=e)
        for t in empTasks:
            counter += 1
        if counter < maxTaskNum:
            availableEmployee.append(e)

    context = {
        "role": role,
        "room_services": room_services,
        "curGuest": curGuest,
        "curBooking": curBooking,
        "curRoom": curRoom,
        "curRoomServices": curRoomServices
    }

    if request.method == "POST":
        try:
            if "foodReq" in request.POST:
                service_type = 'Food'
                newServiceReq = RoomServices(
                    curBooking=curBooking, price=50.0, room=curRoom, servicesType=service_type)
                newServiceReq.save()

                if availableEmployee:
                    chosenEmp = random.choice(availableEmployee)
                else:
                    chosenEmp = Employee.objects.first()
                lastTask = Task.objects.filter(employee=chosenEmp).last() if chosenEmp else None
                if lastTask is not None:
                    Task.objects.create(employee=chosenEmp, room=curRoom, startTime=lastTask.endTime,
                                        endTime=lastTask.endTime+datetime.timedelta(minutes=30),
                                        description=f"{service_type} Request - Room {curRoom.number}", category='food')
                else:
                    Task.objects.create(employee=chosenEmp, room=curRoom, startTime=datetime.datetime.now(),
                                        endTime=datetime.datetime.now()+datetime.timedelta(minutes=30),
                                        description=f"{service_type} Request - Room {curRoom.number}", category='food')
                return redirect("current-room-services")

            if "cleaningReq" in request.POST:
                service_type = 'Cleaning'
                newServiceReq = RoomServices(
                    curBooking=curBooking, price=0.0, room=curRoom, servicesType=service_type)
                newServiceReq.save()
                if availableEmployee:
                    chosenEmp = random.choice(availableEmployee)
                else:
                    chosenEmp = Employee.objects.first()
                lastTask = Task.objects.filter(employee=chosenEmp).last() if chosenEmp else None
                if lastTask is not None:
                    Task.objects.create(employee=chosenEmp, room=curRoom, startTime=lastTask.endTime,
                                        endTime=lastTask.endTime+datetime.timedelta(minutes=30),
                                        description=f"{service_type} Request - Room {curRoom.number}", category='cleaning')
                else:
                    Task.objects.create(employee=chosenEmp, room=curRoom, startTime=datetime.datetime.now(),
                                        endTime=datetime.datetime.now()+datetime.timedelta(minutes=30),
                                        description=f"{service_type} Request - Room {curRoom.number}", category='cleaning')
                return redirect("current-room-services")

            if "amenitiesReq" in request.POST:
                service_type = 'Amenities'
                newServiceReq = RoomServices(
                    curBooking=curBooking, price=0.0, room=curRoom, servicesType=service_type)
                newServiceReq.save()
                if availableEmployee:
                    chosenEmp = random.choice(availableEmployee)
                else:
                    chosenEmp = Employee.objects.first()
                lastTask = Task.objects.filter(employee=chosenEmp).last() if chosenEmp else None
                if lastTask is not None:
                    Task.objects.create(employee=chosenEmp, room=curRoom, startTime=lastTask.endTime,
                                        endTime=lastTask.endTime+datetime.timedelta(minutes=30),
                                        description=f"{service_type} Request - Room {curRoom.number}", category='maintenance')
                else:
                    Task.objects.create(employee=chosenEmp, room=curRoom, startTime=datetime.datetime.now(),
                                        endTime=datetime.datetime.now()+datetime.timedelta(minutes=30),
                                        description=f"{service_type} Request - Room {curRoom.number}", category='maintenance')
                return redirect("current-room-services")

            if "techReq" in request.POST:
                service_type = 'Technical'
                newServiceReq = RoomServices(
                    curBooking=curBooking, price=0.0, room=curRoom, servicesType=service_type)
                newServiceReq.save()
                if availableEmployee:
                    chosenEmp = random.choice(availableEmployee)
                else:
                    chosenEmp = Employee.objects.first()
                lastTask = Task.objects.filter(employee=chosenEmp).last() if chosenEmp else None
                if lastTask is not None:
                    Task.objects.create(employee=chosenEmp, room=curRoom, startTime=lastTask.endTime,
                                        endTime=lastTask.endTime+datetime.timedelta(minutes=30),
                                        description=f"{service_type} Request - Room {curRoom.number}", category='maintenance')
                else:
                    Task.objects.create(employee=chosenEmp, room=curRoom, startTime=datetime.datetime.now(),
                                        endTime=datetime.datetime.now()+datetime.timedelta(minutes=30),
                                        description=f"{service_type} Request - Room {curRoom.number}", category='maintenance')
                return redirect("current-room-services")
        except Exception as e:
            messages.error(request, f"Service request failed: {e}")
            return redirect("current-room-services")

    return render(request, path + "current-room-services.html", context)


@login_required(login_url='login')
def bookings(request):
    import datetime
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    path = role + "/"

    bookings = Booking.objects.all()
    # calculating total for every booking:
    totals = {}  # <booking : total>
    for booking in bookings:
        start_date = datetime.datetime.strptime(
            str(booking.startDate), "%Y-%m-%d")
        end_date = datetime.datetime.strptime(str(booking.endDate), "%Y-%m-%d")
        numberOfDays = abs((end_date-start_date).days)
        # get room peice:
        price = Room.objects.get(number=booking.roomNumber.number).price
        total = price * numberOfDays
        totals[booking] = total

    if request.method == "POST":
        if "filter" in request.POST:
            if (request.POST.get("number") != ""):
                rooms = Room.objects.filter(
                    number__contains=request.POST.get("number"))
                bookings = bookings.filter(
                    roomNumber__in=rooms)

            if (request.POST.get("name") != ""):
                users = User.objects.filter(
                    Q(first_name__contains=request.POST.get("name")) | Q(last_name__contains=request.POST.get("name")))
                guests = Guest.objects.filter(user__in=users)
                bookings = bookings.filter(
                    guest__in=guests)

            if (request.POST.get("rez") != ""):
                bookings = bookings.filter(
                    dateOfReservation=request.POST.get("rez"))

            if (request.POST.get("fd") != ""):
                bookings = bookings.filter(
                    startDate__gte=request.POST.get("fd"))

            if (request.POST.get("ed") != ""):
                bookings = bookings.filter(
                    endDate__lte=request.POST.get("ed"))

            context = {
                "role": role,
                'bookings': bookings,
                'totals': totals,
                "name": request.POST.get("name"),
                "number": request.POST.get("number"),
                "rez": request.POST.get("rez"),
                "fd": request.POST.get("fd"),
                "ed": request.POST.get("ed")
            }

            return render(request, path + "bookings.html", context)

    context = {
        "role": role,
        'bookings': bookings,
        'totals': totals
    }
    return render(request, path + "bookings.html", context)


@login_required(login_url='login')
def booking_make(request):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    path = role + "/"

    if request.method != 'POST':
        messages.warning(request, "Please select a room and check-in/check-out dates.")
        return redirect("rooms")

    guests = Guest.objects.all()  # we pass this to context
    names = []
    if request.method == 'POST':
        if not all(request.POST.get(field) for field in ("roomid", "fd", "ld")):
            messages.warning(request, "Please select a room and check-in/check-out dates.")
            return redirect("rooms")

        try:
            room = Room.objects.get(number=request.POST.get("roomid"))
            start_date = datetime.strptime(request.POST.get("fd"), "%Y-%m-%d").date()
            end_date = datetime.strptime(request.POST.get("ld"), "%Y-%m-%d").date()
        except (Room.DoesNotExist, ValueError, TypeError):
            messages.warning(request, "Please select a valid room and check-in/check-out dates.")
            return redirect("rooms")
        today = date.today()
        if start_date < today:
            messages.error(request, "Check-in date cannot be in the past.")
            return redirect("rooms")
        if end_date <= start_date:
            messages.error(request, "Check-out date must be after check-in date.")
            return redirect("rooms")
        if room_unavailable_for_dates(room, start_date, end_date):
            messages.error(request, "This room is already booked/occupied for the selected dates.")
            return redirect("rooms")

        total_price = 0.0
        base_total = 0.0
        nightly_prices = []
        current_date = start_date

        while current_date < end_date:
            base_rate = round(float(room.price), 2)
            markup = seasonal_markup_for_date(current_date)
            nightly_rate = round(base_rate * (1 + markup / 100), 2)
            total_price += nightly_rate
            base_total += base_rate
            nightly_prices.append({
                "date": current_date,
                "base_rate": base_rate,
                "markup": markup,
                "rate": nightly_rate,
            })
            current_date += timedelta(days=1)

        total = total_price
        numberOfDays = (end_date-start_date).days
        if 'add' in request.POST:  # add dependee
            name = request.POST.get("depName")
            names.append(name)
            for i in range(room.capacity-2):
                nameid = "name" + str(i+1)
                if request.POST.get(nameid) != "":
                    names.append(request.POST.get(nameid))

        if 'bookGuestButton' in request.POST:
            if "guest" in request.POST:
                curguest = Guest.objects.get(id=request.POST.get("guest"))
            else:
                curguest = request.user.guest
            curbooking = Booking(
                guest=curguest,
                roomNumber=room,
                startDate=start_date,
                endDate=end_date,
                total_price=total,
            )
            curbooking.save()

            for i in range(room.capacity-1):
                nameid = "name" + str(i+1)
                if request.POST.get(nameid) != "":
                    if request.POST.get(nameid) != None:
                        d = Dependees(booking=curbooking,
                                      name=request.POST.get(nameid))
                        d.save()
            request.session["booking_id"] = curbooking.id
            request.session.pop("payment_code", None)
            return redirect("payment")

    context = {
        "fd": request.POST.get("fd"),
        "ld": request.POST.get("ld"),
        "role": role,
        "guests": guests,
        "room": room,
        "total": total,
        "base_total": base_total,
        "numberOfDays": numberOfDays,
        "nightly_prices": nightly_prices,
        "names": names
    }

    return render(request, path + "booking-make.html", context)


@login_required(login_url='login')
def deleteBooking(request, pk):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    path = role + "/"

    booking = Booking.objects.get(id=pk)
    if request.method == "POST":
        booking.delete()
        return redirect('bookings')

    context = {
        "role": role,
        'booking': booking

    }
    return render(request, path + "deleteBooking.html", context)


@ login_required(login_url='login')
def refunds(request):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    path = role + "/"

    refunds = Refund.objects.all()
    context = {
        "role": role,
        'refunds': refunds
    }

    if request.method == "POST":
        if "decline" in request.POST or "approve" in request.POST:
            refundId = request.POST.get("refund", "")
            guestUserId = request.POST.get("guestUserId", "")

            tempUser = User.objects.get(id=guestUserId)
            receiver = Guest.objects.get(user=tempUser)

            def send(request, receiver, text, subject):

                message_email = 'hms@support.com'
                message = text
                receiver_name = receiver.user.first_name + " " + receiver.user.last_name

                # send email
                send_mail(
                    receiver_name + " " + subject,   # subject
                    message,                          # message
                    message_email,                    # from email
                    [receiver.user.email],                    # to email
                    fail_silently=False,              # for user in users :
                    # user.email
                )

                messages.success(
                    request, 'Feedback E-Mail Was Successfully Sent')

                Refund.objects.filter(id=refundId).delete()
                return render(request, path + "refunds.html", context)

            def send_mail_refund_approved(request, receiver):
                subject = "Refund"
                text = """
                    Dear {guestName},
                    We are pleased to confirm that your refund request has been accepted.
                    The amount of refund will be on your account in 24 hours.
                    This time interval can change up to 48 hours according to your bank.
                    We are very sorry for this inconvenience. We hope to see you soon.
                """
                email_text = text.format(
                    guestName=receiver.user.first_name + " " + receiver.user.last_name)

                send(request, receiver, email_text, subject)

            def send_mail_refund_declined(request, receiver):
                subject = "Refund"
                text = """
                    Dear {guestName},
                    We are sorry to inform you that your refund request has been declined.
                    After our examinations, we see that your request can not be done according to our Hotel Policy.
                    We are very sorry for this inconvenience. We hope to see you soon.
                """
                email_text = text.format(
                    guestName=receiver.user.first_name + " " + receiver.user.last_name)

                send(request, receiver, email_text, subject)

            if "decline" in request.POST:
                send_mail_refund_declined(request, receiver)
            if "approve" in request.POST:
                send_mail_refund_approved(request, receiver)

            refundId = None
            statu = None

        if "filter" in request.POST:
            users = User.objects.all()
            if (request.POST.get("gid") != ""):
                users = users.filter(
                    id__contains=request.POST.get("gid"))
                guests = Guest.objects.filter(user__in=users)
                refunds = refunds.filter(guest__in=guests)

            if (request.POST.get("name") != ""):
                users = users.filter(
                    Q(first_name__contains=request.POST.get("name")) | Q(last_name__contains=request.POST.get("name")))
                guests = Guest.objects.filter(user__in=users)
                refunds = refunds.filter(guest__in=guests)

            if (request.POST.get("booking") != ""):
                booking = Booking.objects.get(id=request.POST.get("booking"))
                refunds = refunds.filter(reservation=booking)

            if (request.POST.get("reason") != ""):
                refunds = refunds.filter(
                    reason__contains=request.POST.get("reason"))

            context = {
                "role": role,
                "refunds": refunds,
                "gid": request.POST.get("gid"),
                "name": request.POST.get("name"),
                "booking": request.POST.get("booking"),
                "reason": request.POST.get("reason")
            }
            return render(request, path + "refunds.html", context)

    return render(request, path + "refunds.html", context)


@login_required(login_url='login')
def request_refund(request):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    path = role + "/"

    curGuest = Guest.objects.get(user=request.user)

    if request.method == "POST":
        if "sendReq" in request.POST:
            reason = request.POST.get("reqExp")
            curBookingId = request.POST.get("bid")
            currentBooking = Booking.objects.get(id=curBookingId)
            temp = Refund.objects.filter(reservation=currentBooking)
            if not temp:
                currentReq = Refund(
                    guest=curGuest, reservation=currentBooking, reason=reason)
                currentReq.save()
                messages.success(
                    request, "Your request was successfully sent.")
            else:
                messages.error(
                    request, "We already have your refund request for this reservation!")

    context = {
        "role": role,
        "curGuest": curGuest,
        "id": request.POST.get("bookingId")
    }

    return render(request, path + "request-refund.html", context)

@login_required(login_url='login')
def checkout(request, pk):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    if role not in ('manager', 'admin', 'receptionist', 'guest'):
        return redirect('rooms')
    room = Room.objects.get(number=pk)
    from django.utils import timezone
    from datetime import timedelta
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)

    # Update active booking end date to yesterday so it is no longer active today
    active_bookings = Booking.objects.filter(roomNumber=room, startDate__lte=today, endDate__gte=today)
    for b in active_bookings:
        b.endDate = yesterday
        b.save()

    # Reset static room fields as backup
    room.status = 'cleaning'
    room.statusStartDate = None
    room.statusEndDate = None
    room.save()
    # Auto-assign housekeeping task
    try:
        from housekeeping_utils import assign_housekeeping_task
        assign_housekeeping_task(room)
    except Exception:
        pass
    messages.success(request, f"Checked out Room {room.number}.")
    return redirect('rooms')


@login_required(login_url='login')
def mark_cleaned(request, pk):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    if role not in ('manager', 'admin', 'receptionist', 'guest'):
        return redirect('rooms')
    room = Room.objects.get(number=pk)
    room.status = 'available'
    room.statusStartDate = None
    room.statusEndDate = None
    room.save()
    messages.success(request, f"Room {room.number} marked cleaned.")
    try:
        from housekeeping_utils import rebalance_cleaning_tasks
        rebalance_cleaning_tasks()
    except Exception:
        pass
    return redirect('rooms')


@login_required(login_url='login')
def delete_room(request, pk):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    if role not in ('manager', 'admin', 'receptionist'):
        return redirect('rooms')
    room = Room.objects.get(number=pk)
    if request.method == 'POST':
        room_number = room.number
        room.delete()
        messages.success(request, f"Room {room_number} deleted successfully.")
        return redirect('rooms')
    return redirect('rooms')


@login_required(login_url='login')
def housekeeping_dashboard(request):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    path = role + "/"
    today = date.today()

    cleaning_tasks = list(Task.objects.filter(category='cleaning').select_related('room', 'employee'))
    for t in cleaning_tasks:
        if t.room:
            t.room_number = str(t.room.number)
        else:
            match = re.search(r'Room\s*(\d+)', t.description or '', re.IGNORECASE)
            t.room_number = match.group(1) if match else 'N/A'
    active_tasks = [t for t in cleaning_tasks if t.status in ['pending', 'in_progress']]
    completed_tasks = [t for t in cleaning_tasks if t.status == 'completed']

    total_pending = len(active_tasks)
    total_in_progress = sum(t.status == 'in_progress' for t in active_tasks)
    completed_today = len(completed_tasks)

    if request.method == 'POST':
        if 'rebalance' in request.POST:
            try:
                from housekeeping_utils import rebalance_cleaning_tasks
                rebalance_count = rebalance_cleaning_tasks()
                messages.info(request, f"Rebalanced {rebalance_count} pending tasks.")
            except Exception as e:
                messages.error(request, f"Rebalance failed: {e}")
            return redirect('housekeeping_dashboard')

    context = {
        'role': role,
        'cleaning_tasks': cleaning_tasks,
        'active_tasks': active_tasks,
        'completed_tasks': completed_tasks,
        'total_pending': total_pending,
        'total_in_progress': total_in_progress,
        'completed_today': completed_today,
    }
    return render(request, "staff/housekeeping.html", context)


@login_required(login_url='login')
def start_cleaning_task(request, task_id):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    if role not in ('manager', 'admin', 'receptionist', 'staff', 'housekeeping'):
        return redirect('rooms')
    # Try task ID first; fall back to room number
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        try:
            task = Task.objects.filter(room__number=task_id, status__in=['pending', 'in_progress']).first()
            if not task:
                task = Task.objects.filter(room__number=task_id, category='cleaning').order_by('-startTime').first()
        except Exception:
            task = None
    if not task:
        # No task found by ID or room number — try to find/create a task for this room
        room = None
        try:
            room = Room.objects.get(number=task_id)
        except Room.DoesNotExist:
            try:
                room = Room.objects.get(id=task_id)
            except Room.DoesNotExist:
                room = None
        if room:
            task, created = Task.objects.get_or_create(
                room=room,
                category='cleaning',
                defaults={'status': 'pending', 'employee': None}
            )
            if not created and task.status == 'completed':
                task.status = 'pending'
                task.save()
        else:
            from django.shortcuts import get_object_or_404
            task = get_object_or_404(Task, id=task_id)
    task.status = 'in_progress'
    task.save()
    messages.info(request, f"Started cleaning Room {task.room.number if task.room else '?'}.")
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'housekeeping_dashboard'
    return redirect(next_url)


@login_required(login_url='login')
def mark_room_cleaned_task(request, task_id):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    if role not in ('manager', 'admin', 'receptionist', 'staff', 'housekeeping'):
        return redirect('rooms')
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        task = Task.objects.filter(room__number=task_id, category='cleaning').order_by('-startTime').first()
    if not task:
        from django.shortcuts import get_object_or_404
        task = get_object_or_404(Task, id=task_id)
    task.status = 'completed'
    task.endTime = timezone.now()
    task.save()
    if task.room:
        task.room.status = 'available'
        task.room.save()
    messages.success(request, f"Room {task.room.number if task.room else '?'} marked cleaned via task.")
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'housekeeping_dashboard'
    return redirect(next_url)

@login_required(login_url='login')
def staff_dashboard(request):
    user_groups = request.user.groups.all()
    role = str(user_groups[0]) if user_groups.exists() else 'guest'
    if role != 'staff':
        return redirect('rooms')
    today = date.today()

    active_requests = list(Task.objects.filter(
        category__in=['food', 'maintenance', 'amenities', 'technical'],
        status__in=['pending', 'in_progress']
    ).select_related('room', 'employee'))

    completed_today = list(Task.objects.filter(
        category__in=['food', 'maintenance', 'amenities', 'technical'],
        status='completed',
        endTime__date=today
    ).select_related('room', 'employee'))

    for task in active_requests + completed_today:
        if task.room:
            task.room_number = str(task.room.number)
        else:
            match = re.search(r'Room\s*[-:\s]*(\d+)', task.description or '', re.IGNORECASE)
            task.room_number = match.group(1) if match else 'N/A'

    context = {
        'role': role,
        'active_requests': active_requests,
        'completed_today': completed_today,
        'active_count': len(active_requests),
        'completed_count': len(completed_today),
    }
    return render(request, 'staff/dashboard.html', context)


@login_required(login_url='login')
def rebalance_housekeeping_tasks(request):
    try:
        from housekeeping_utils import rebalance_cleaning_tasks
        rebalance_cleaning_tasks()
        messages.info(request, "Housekeeping workload rebalanced.")
    except Exception as e:
        messages.error(request, f"Rebalance failed: {e}")
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'housekeeping_dashboard'
    return redirect(next_url)
