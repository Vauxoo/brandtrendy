===================================================
Brandtrendy · Promocionales (sitio de cotización)
===================================================

Reproduce el sitio «Promocionales Brandtrendy» sobre el estándar de Odoo 19 al instalarse o actualizarse, sin pasos
manuales: el sitio opera por **solicitud de cotización**, no por compra.

Qué hace
========

* **Configuración del sitio** (``data/aplicar.xml`` → ``website._bt_promo_aplicar``, en cada instalación y
  actualización): modo cotización, tema propio del sitio (paleta, Hanken Grotesk autoalojada, iconos, favicon) cargado
  solo en ese sitio, vistas heredadas de la versión 17 apagadas, código inyectado vaciado, ajustes del sitio, textos de
  los pasos del checkout y paso «Información adicional». El sitio se resuelve por su nombre, nunca por id. El resultado
  de cada paso queda en el parámetro ``brandtrendy_promo_theme.ultimo_aplicar``.
* **Checkout de cotización**: sin el paso de facturación (CFDI) en el sitio en modo cotización; los datos fiscales se
  piden al confirmar el pedido.
* **Solicitud → lead en servidor** (``data/automatizacion.xml``): cuando la orden del sitio recibe un contacto real se
  crea o se liga un lead; cuando la solicitud se confirma se actualiza ese mismo lead, se agenda la cotización y se avisa
  al equipo. Sin JavaScript propio.
* **Acuse al cliente** con la voz de la casa en lugar del correo estándar de pago (solo en el sitio en modo cotización).
* **Cantidad inicial = mínimo de compra** en la ficha del producto.

Importante
==========

* **No desinstalar.** Este módulo declara los campos ``x_bt_*`` de leads, órdenes y productos que ya existían en la base;
  desinstalarlo borraría esas columnas con sus datos.
* El acuse por WhatsApp está apagado por omisión: se enciende con el parámetro
  ``brandtrendy_promo_theme.acuse_whatsapp = 1`` (manda mensajes a clientes).
* Repositorio público: nada de credenciales, proveedores, costos ni datos de clientes en este módulo.
* **Copias por sitio y builds en rojo.** Al terminar cada actualización, Odoo 19 copia toda vista genérica nueva bajo
  todas las copias por sitio de su vista padre (activas o no) y la valida ahí; una copia sin las anclas de 19 aborta la
  actualización (Odoo.sh: «Test: Failed»), aunque el sitio responda. Por eso:

  - el paso ``jubilar`` cambia la key (sufijo ``.bt17_jubilada``) de las copias inactivas de la 17 de plantillas
    primarias que el paso ``vistas`` apaga, con su subárbol del sitio. No cambia nada visible. Reversa: quitar el sufijo
    (solo junto con quitar este paso; si no, la siguiente actualización vuelve a fallar);
  - el paso ``herencias_sitio`` hace por adelantado esas copias para las vistas de este módulo y, si una no valida,
    deja un marcador inactivo y un aviso en el log: la personalización no aplica en esa copia hasta revisarla;
  - antes de dar por bueno un build: ``odoo19/tools/f5_diagnostico_cow.py --modulos '*'`` (0 errores) y el estado del
    build en Odoo.sh.
* En producción, Odoo.sh solo actualiza un módulo si sube ``version`` en el manifiesto: subirla en cada entrega.
* Desinstalar este módulo arrastra al kit ``brandtrendy`` (depende de él); las copias jubiladas no se revierten solas.
