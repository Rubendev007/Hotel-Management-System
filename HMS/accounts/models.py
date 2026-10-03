from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
from django.contrib.auth.models import User
# Create your models here.


class Guest(models.Model):
    user = models.OneToOneField(User, null=True, on_delete=models.CASCADE)
    phoneNumber = PhoneNumberField(unique=True)

    def __str__(self):
        return str(self.user)

    def numOfBooking(self):
        return self.booking_set.all().count()

    def numOfDays(self):
        totalDay = 0
        bookings = self.booking_set.all()
        for b in bookings:
            day = b.endDate - b.startDate
            totalDay += int(day.days)

        return totalDay

    def numOfLastBookingDays(self):
        try:
            return int((self.booking_set.all().last().endDate - self.booking_set.all().last().startDate).days)
        except:
            return 0

    def currentRoom(self):
        booking = self.booking_set.all().last()
        return booking.roomNumber if booking is not None else None


class Employee(models.Model):
    user = models.OneToOneField(User, null=True, on_delete=models.CASCADE)
    phoneNumber = PhoneNumberField(unique=True)
    salary = models.FloatField()

    def __str__(self):
        return str(self.user)


class Task(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]
    CATEGORY_CHOICES = [
        ('cleaning', 'Housekeeping / Cleaning'),
        ('food', 'In-Room Dining / Food Order'),
        ('maintenance', 'Technical / Maintenance'),
        ('general', 'General Task'),
    ]
    employee = models.ForeignKey(
        Employee, null=True, on_delete=models.CASCADE)
    room = models.ForeignKey(
        'room.Room', null=True, blank=True, on_delete=models.SET_NULL)
    startTime = models.DateTimeField(auto_now_add=True)
    endTime = models.DateTimeField(null=True, blank=True)
    description = models.TextField()
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending')
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default='general')

    def __str__(self):
        return str(self.employee)
