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
    employee = models.ForeignKey(
        Employee,   null=True, on_delete=models.CASCADE)
    startTime = models.DateTimeField()
    endTime = models.DateTimeField()
    description = models.TextField()

    def str(self):
        return str(self.employee)
