from django.contrib import admin
from .models import *

# Register your models here.
class RoomAdmin(admin.ModelAdmin):
    fields = ('number', 'capacity', 'numberOfBeds', 'roomType', 'price',
              'statusStartDate', 'statusEndDate', 'image')

admin.site.register(Room, RoomAdmin)
admin.site.register(Booking)
admin.site.register(Dependees)
admin.site.register(RoomServices)
admin.site.register(Refund)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "markup_percentage", "is_active")

admin.site.register(Season, SeasonAdmin)
