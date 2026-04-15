# api/app/openapi_tags.py — Metadatos de tags para la documentación OpenAPI/Swagger
# Define las secciones que aparecen en la documentación interactiva de la API

tags_metadata = [
    {"name": "Health", "description": "Estado del servicio"},
    {"name": "Channel", "description": "Gestion de canales/sesiones de WhatsApp"},
    {"name": "Users", "description": "Autenticacion y perfil de usuario"},
    {"name": "Settings", "description": "Configuracion del canal"},
    {"name": "Messages", "description": "Envio y gestion de mensajes"},
    {"name": "Chats", "description": "Gestion de conversaciones"},
    {"name": "Contacts", "description": "Gestion de contactos"},
    {"name": "Presences", "description": "Estado de presencia"},
    {"name": "Groups", "description": "Gestion de grupos"},
    {"name": "Stories", "description": "Estados/Historias de WhatsApp"},
    {"name": "Statuses", "description": "Estados de visualizacion (ACK)"},
    {"name": "Newsletters", "description": "Canales de WhatsApp (Threads)"},
    {"name": "Media", "description": "Gestion de archivos multimedia"},
    {"name": "Business", "description": "Funciones de WhatsApp Business"},
    {"name": "Labels", "description": "Etiquetas de WhatsApp"},
    {"name": "Blacklist", "description": "Lista negra de contactos"},
    {"name": "Communities", "description": "Comunidades de WhatsApp"},
    {"name": "Calls", "description": "Gestion de llamadas"},
    {"name": "Webhooks", "description": "Suscripciones a eventos"},
]
