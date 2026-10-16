from django.urls import path

from . import views

urlpatterns = [
    path("webhooks/razorpay/", views.razorpay_webhook, name="razorpay-webhook"),
]
