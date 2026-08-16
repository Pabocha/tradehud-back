from django.urls import path
from . import views

app_name = 'support'

urlpatterns = [
    # ---- Côté client (front e-commerce) ----
    path('tickets/', views.TicketListCreateView.as_view(), name='ticket-list-create'),
    path('tickets/<int:ticket_id>/', views.TicketDetailView.as_view(), name='ticket-detail'),
    path('tickets/<int:ticket_id>/messages/', views.TicketMessageCreateView.as_view(), name='ticket-message-create'),

    # ---- Plateforme dédiée (rôles support/admin) ----
    path('admin/tickets/', views.TicketAdminListView.as_view(), name='admin-ticket-list'),
    path('admin/tickets/<int:ticket_id>/', views.TicketAdminDetailView.as_view(), name='admin-ticket-detail'),
    path('admin/tickets/<int:ticket_id>/assign/', views.TicketAdminAssignView.as_view(), name='admin-ticket-assign'),
    path('admin/tickets/<int:ticket_id>/status/', views.TicketAdminStatusView.as_view(), name='admin-ticket-status'),
    path('admin/tickets/<int:ticket_id>/messages/', views.TicketAdminMessageCreateView.as_view(), name='admin-ticket-message-create'),
]
