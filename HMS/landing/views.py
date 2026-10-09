# landing/views.py
from django.shortcuts import render

# Unsplash images (free to use under the Unsplash License).
# To swap a photo: open it on unsplash.com, copy the ID from the image URL
# (images.unsplash.com/photo-XXXX) and keep the same query string.
def u(photo_id, w=1920):
    return f"https://images.unsplash.com/{photo_id}?auto=format&fit=crop&w={w}&q=80"

HERO = u("photo-1542314831-068cd1dbfeeb")      # luxury hotel exterior/lobby
BG = u("photo-1566073771259-6a8506099945")     # resort hotel with pool

FEATURES = [
    {
        "title": "Reservations and front desk",
        "description": "Take bookings from every channel, check guests in and out in seconds, and see room availability at a glance without double bookings.",
        "image": u("photo-1551882547-ff40c63fe5fa", 1400),
    },
    {
        "title": "Rooms and housekeeping",
        "description": "Assign cleaning tasks, track room status in real time and flag maintenance issues so every room is ready before the guest arrives.",
        "image": u("photo-1590490360182-c33d57733427", 1400),
    },
    {
        "title": "Billing, reports and guest stays",
        "description": "Create invoices, split bills and accept payments, then follow occupancy, revenue and guest history from one clear dashboard.",
        "image": u("photo-1520250497591-112f2f40a3f4", 1400),
    },
]

def index(request):
    return render(request, "landing/index.html", {
        "brand": "CrewMates",
        "hero_image": HERO,
        "bg_image": BG,
        "features": FEATURES,
    })

# landing/urls.py  ->  path("", views.index, name="landing")