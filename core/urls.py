from django.urls import path
from . import monitoring_views, views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    path('customers/', views.customer_list, name='customer_list'),
    path('customers/new/', views.customer_create, name='customer_create'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('customers/<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('api/customers/search/', views.customer_search_api, name='customer_search_api'),

    path('products/', views.product_list, name='product_list'),
    path('products/new/', views.product_create, name='product_create'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('api/products/<int:pk>/price/', views.product_price_api, name='product_price_api'),

    path('sales/', views.sale_list, name='sale_list'),
    path('sales/new/', views.sale_create, name='sale_create'),
    path('sales/<int:pk>/', views.sale_detail, name='sale_detail'),
    path('sales/<int:pk>/edit/', views.sale_edit, name='sale_edit'),
    path('sales/<int:pk>/void/', views.sale_void, name='sale_void'),

    path('reports/', views.reports, name='reports'),
    path('reports/sales.csv', views.sales_csv, name='sales_csv'),
    path('reports/sales.xlsx', views.sales_excel, name='sales_excel'),

    path('monitoring/', monitoring_views.monitoring_list, name='monitoring_list'),
    path('monitoring/new/', monitoring_views.monitoring_create, name='monitoring_create'),
    path('monitoring/export.csv', monitoring_views.monitoring_csv, name='monitoring_csv'),
    path('monitoring/<int:pk>/', monitoring_views.monitoring_detail, name='monitoring_detail'),
    path('monitoring/<int:pk>/edit/', monitoring_views.monitoring_edit, name='monitoring_edit'),

    path('team/', views.user_list, name='user_list'),
    path('team/new/', views.user_create, name='user_create'),
    path('team/<int:pk>/', views.user_detail, name='user_detail'),
    path('team/<int:pk>/edit/', views.user_edit, name='user_edit'),

    path('settings/', views.settings_view, name='settings'),
    path('audit/', views.audit_list, name='audit_list'),
    path('audit/<int:pk>/', views.audit_detail, name='audit_detail'),
    path('backup/', views.backup_center, name='backup_center'),
    path('backup/download/', views.backup_export, name='backup_export'),
    path('backup/restore/', views.backup_restore, name='backup_restore'),

    path('zones/', views.zone_list, name='zone_list'),
    path('zones/new/', views.zone_create, name='zone_create'),
    path('zones/<int:pk>/', views.zone_detail, name='zone_detail'),
    path('zones/<int:pk>/edit/', views.zone_edit, name='zone_edit'),

    path('roles/', views.role_list, name='role_list'),
    path('roles/<int:pk>/edit/', views.role_edit, name='role_edit'),

    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('help/', views.help_view, name='help'),
]
