from django.contrib import admin
from django.urls import path, include
from main import views

urlpatterns = [
    path('', views.ping, name="ping"),
    path('ping', views.ping, name="ping"),
    path('get_interesting_posts', views.get_interesting_posts, name="get_interesting_posts"),
    path('get_post_category', views.get_post_category, name="get_post_category"),
    path('get_author_category', views.get_author_category, name="get_author_category")
]