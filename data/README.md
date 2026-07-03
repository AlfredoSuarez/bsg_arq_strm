# Datos reales del laboratorio

Esta carpeta contiene `ecommerce_orders_dataset.csv`, el dataset real usado por el MCP de datos. Tiene 30.000 órdenes, 8.683 clientes y 41 atributos de transacción, producto, cliente, logística, experiencia y rentabilidad.

No se usan datos ficticios en esta versión. Antes de iniciar `mcp_datos.py`, convierte el CSV a SQLite:

```bash
python data/import_dataset_to_sqlite.py
```

El script genera `ecommerce_orders.db`, que no se versiona porque puede reconstruirse desde el CSV. La tabla SQLite se llama `orders` y conserva los nombres de columna del archivo CSV original.

El dataset incluye datos de ejemplo para fines formativos. No debe tratarse como una fuente de decisiones comerciales reales.
