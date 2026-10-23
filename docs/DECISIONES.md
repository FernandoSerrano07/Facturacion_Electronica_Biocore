# Decisiones iniciales para FacturaPro 2.0 / BIOCORE

Estas son reglas de producto acordadas para implementar en PRs futuros. **No indican funcionalidades ya terminadas.**

## Plataforma de creadores

- Portal privado de propietarios y soporte técnico para dar de alta empresas.
- Activación de módulos opcionales por empresa, con límites y planes asignados.
- Deshabilitar módulos oculta y deniega su uso sin borrar los datos del cliente.
- Los permisos de módulo se comprueban en el backend además de la interfaz.
- El acceso extraordinario del personal de soporte a una empresa requiere autorización, duración limitada y auditoría.

## Usuarios y operación

- Cuenta de vendedor vinculada a sucursal y horarios específicos; bloqueos por vacaciones y asuetos.
- **Cumpleaños de vendedores:** listado interno visible únicamente por gerente y subgerente; no mostrar edades, felicitaciones, antigüedad ni cuentas regresivas en el dashboard.
- **Comisiones:** calculadas sobre el subtotal sin IVA y registradas en reportes internos.
- Precios de costo y venta con tratamiento de IVA explícito; guardar costos históricos por venta.
- Los estados de DTE deben reflejar la respuesta real de Hacienda; no marcar como aceptado un documento pendiente o rechazado.

## Identidad visual

- Mantener BIOCORE como identidad visual propuesta: verde `#00A37F`, oscuro `#13261F`, tipografía Archivo.
- Compartir componentes de interfaz entre portal de creadores y paneles de empresa.
- Aclarar denominación final entre plataforma BIOCORE y producto FacturaPro antes de publicar.

## Seguridad y datos

- No mezclar datos entre empresas; UUID validado antes de seleccionar schema por transacción.
- Conservación de secretos en variables de entorno, jamás en Git ni en respuestas API.
- Antes de migrar la versión PHP/MySQL, respaldar y validar integridad de la base de datos actual.
- DTE y certificados sujetos a validación de las especificaciones y el ambiente oficial vigente de El Salvador.
