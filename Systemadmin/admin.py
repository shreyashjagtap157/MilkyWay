from django.contrib import admin
from .models import Systemadmin, UniquePhoneNumber, NotificationLog, NotificationPreference


@admin.register(Systemadmin)
class SystemadminAdmin(admin.ModelAdmin):
    list_display = ['username', 'is_active', 'is_staff', 'is_superuser']
    search_fields = ['username']
    list_filter = ['is_active', 'is_staff', 'is_superuser']


@admin.register(UniquePhoneNumber)
class UniquePhoneNumberAdmin(admin.ModelAdmin):
    list_display = ['phone_number', 'user_type', 'user_id', 'created_at', 'updated_at']
    search_fields = ['phone_number']
    list_filter = ['user_type', 'created_at']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('title', 'recipient')


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'receive_promotions', 'receive_updates')
    list_filter = ('receive_promotions', 'receive_updates')
    search_fields = ('user__username',)

