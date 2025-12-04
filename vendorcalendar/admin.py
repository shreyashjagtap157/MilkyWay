from django.contrib import admin
from .models import DeliveryRecord, CustomerRequest, MilkmanLeaveRequest


@admin.register(DeliveryRecord)
class DeliveryRecordAdmin(admin.ModelAdmin):
    list_display = ['customer', 'vendor', 'milkman', 'date', 'status']
    list_filter = ['status', 'date', 'vendor']
    search_fields = ['customer__name', 'vendor__name', 'milkman__name']
    date_hierarchy = 'date'
    ordering = ['-date']
    raw_id_fields = ['customer', 'vendor', 'milkman']


@admin.register(CustomerRequest)
class CustomerRequestAdmin(admin.ModelAdmin):
    list_display = ['customer', 'vendor', 'request_type', 'date', 'status', 'cow_milk_extra', 'buffalo_milk_extra', 'created_at']
    list_filter = ['status', 'request_type', 'date', 'vendor']
    search_fields = ['customer__name', 'vendor__name']
    date_hierarchy = 'date'
    ordering = ['-created_at']
    raw_id_fields = ['customer', 'vendor']
    readonly_fields = ['created_at', 'approved_rejected_at']
    
    fieldsets = (
        ('Request Information', {
            'fields': ('customer', 'vendor', 'request_type', 'date', 'status')
        }),
        ('Details', {
            'fields': ('cow_milk_extra', 'buffalo_milk_extra', 'rejection_reason')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'approved_rejected_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(MilkmanLeaveRequest)
class MilkmanLeaveRequestAdmin(admin.ModelAdmin):
    list_display = ['milkman', 'vendor', 'start_date', 'end_date', 'status', 'reason']
    list_filter = ['status', 'start_date', 'vendor']
    search_fields = ['milkman__name', 'vendor__name', 'reason']
    date_hierarchy = 'start_date'
    ordering = ['-start_date']
    raw_id_fields = ['milkman', 'vendor']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Leave Information', {
            'fields': ('milkman', 'vendor', 'start_date', 'end_date', 'status')
        }),
        ('Details', {
            'fields': ('reason',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
