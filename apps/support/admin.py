from django.contrib import admin
from .models import SupportTicket, SupportTicketMessage


class SupportTicketMessageInline(admin.TabularInline):
    model = SupportTicketMessage
    extra = 0
    readonly_fields = ('user', 'message', 'created_at')


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_number', 'subject', 'user', 'category', 'priority', 'status', 'assigned_to', 'created_at')
    list_filter = ('status', 'priority', 'category')
    search_fields = ('ticket_number', 'subject', 'message', 'user__email')
    inlines = [SupportTicketMessageInline]
    readonly_fields = ('ticket_number', 'created_at', 'updated_at')


@admin.register(SupportTicketMessage)
class SupportTicketMessageAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'user', 'message', 'created_at')
    search_fields = ('message', 'ticket__ticket_number')
