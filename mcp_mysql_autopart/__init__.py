"""
MCP MySQL Autopart - Servidor y cliente de solo lectura para la base de datos autopart.

Tablas disponibles:
  - vehicle_type       : tipos de vehículo (id, vehicle_type_name)
  - vehicles           : vehículos (modelo, fabricante, tipo)
  - product_category   : categorías de producto (jerárquica, con parent)
  - application_status : estados de aplicación/publicación
  - seller             : vendedores (nombre, dirección, teléfono)
  - applications       : publicaciones de autopartes (precio, condición, vendedor, categoría)
  - compatibility      : compatibilidad de piezas con vehículos y rangos de año
"""
