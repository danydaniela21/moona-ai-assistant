# MOONA Connect 0.3

Extensión Chrome Manifest V3 para enviar al Social Hub de MOONA indicadores derivados de los títulos de pestañas autorizadas. El *service worker* consulta al cambiar los títulos, navegar, cerrar pestañas o cambiar permisos. También actualiza al iniciar Chrome y cada minuto mediante una alarma. Abrir el panel o pulsar **Actualizar** fuerza una consulta local.

## Instalar y probar en Chrome

1. Abre `chrome://extensions`, activa **Modo de desarrollador** y pulsa **Cargar descomprimida**.
2. Selecciona la carpeta `experiments/moona_connect/` que contiene `manifest.json`. Abre **MOONA Connect** desde el menú de extensiones.
3. Pulsa **Autorizar** junto a la plataforma que quieras probar y acepta el aviso de Chrome. Reabre el panel si Chrome lo cierra durante la confirmación.
4. Abre el sitio autorizado en el mismo perfil de Chrome. Usa tu sesión habitual y comprueba si el propio sitio muestra un número en el título ante una novedad real. Abre el panel o pulsa **Actualizar** y compara ambos valores.
5. Prueba con un título sin número, cierra la pestaña y revoca el acceso desde los detalles de la extensión en Chrome. Deben aparecer, respectivamente, **Indicador desconocido**, **Sin pestaña detectable** y **Permiso pendiente** al actualizar. Chrome también puede ocultar una pestaña si la configuración de acceso al sitio restringe la lectura.

La extensión requiere Chrome 102 o posterior. Usa permisos opcionales para cuatro hosts HTTPS exactos, además de `nativeMessaging`, `alarms` y `storage`. El almacenamiento local guarda la preferencia de monitoreo y el almacenamiento de sesión conserva los identificadores de plataforma pendientes de una ventana normal. Autorizar un sitio permite a Chrome compartir sus metadatos de pestaña. El código usa la URL para filtrar eventos y comprobar si ya existe una pestaña. Solo analiza los títulos de hosts autorizados. Los títulos completos quedan en memoria durante la consulta. Las páginas abiertas por Chrome usan las sesiones habituales. La extensión no inyecta scripts, lee el DOM, accede a credenciales ni realiza solicitudes de red propias.

## Monitoreo automático

1. Recarga la extensión existente en `chrome://extensions` desde la misma carpeta. Así conservas el ID ya registrado en Native Messaging.
2. Autoriza los sitios deseados y marca **Monitoreo automático** en el panel. La opción empieza desmarcada incluso si ya habías concedido permisos en la versión anterior.
3. Al activar la opción o iniciar el perfil, Chrome abre los sitios autorizados que falten como pestañas inactivas, sin cambiar la pestaña activa ni enfocar otra ventana. Se reutilizan las pestañas detectables del mismo perfil, incluidas las que estén en otra ventana normal, descartadas o navegando hacia un sitio autorizado. Si todavía no hay una ventana normal, la apertura se aplaza hasta que aparezca una.
4. Si concedes un permiso adicional mientras la opción está activa, se prepara solo el sitio recién autorizado. Cerrar una pestaña manualmente actualiza el Social Hub. El monitor no la reabre periódicamente. Puede abrirla de nuevo en el próximo inicio de Chrome o al volver a habilitar el monitoreo.
5. Desmarca la opción para detener las aperturas automáticas. Las pestañas existentes permanecen abiertas y conservan la lectura habitual de indicadores. Para dejar de leer un sitio abierto, retira su permiso desde Chrome.

Durante el arranque se espera brevemente a que Chrome exponga las pestañas restauradas. Chrome no ofrece aquí una operación atómica para consultar y abrir, así que una restauración tardía o una apertura manual simultánea puede producir un duplicado. La extensión nunca cierra pestañas para deduplicar. Outlook sigue fuera del monitoreo.

### Pestañas suspendidas y descarte

Chrome puede congelar páginas, ralentizar sus temporizadores o descartarlas con el ahorro de memoria. Si expone una pestaña como congelada o descartada, MOONA la muestra como **Desconocido** hasta que pueda observar un título utilizable. Chrome expone `frozen` a partir de la versión 132. Una pestaña en segundo plano puede conservar un título antiguo incluso cuando Chrome todavía no la marca como suspendida. La alarma acredita que la extensión publicó una observación, sin garantizar que el sitio haya actualizado su título. La extensión no recarga, fija ni modifica la política de descarte de las pestañas. Chrome permite, por sitio, configurar **Mantener siempre activos estos sitios** en **Rendimiento**. Esa excepción de descarte no obliga a un sitio a actualizar el título. [API de pestañas de Chrome](https://developer.chrome.com/docs/extensions/reference/api/tabs) · [Opciones de rendimiento](https://support.google.com/chrome/answer/12929150)

### Reutilizar una pestaña desde Social Hub

Los enlaces del Social Hub conservan la apertura en una pestaña nueva. Un enlace normal de Streamlit no puede buscar ni activar una pestaña arbitraria que Chrome ya tenga abierta. Para incorporar reutilización, un paso posterior podría enviar una orden desde la página local a la extensión mediante `externally_connectable` y `runtime.sendMessage`. La extensión tendría que verificar el origen exacto de MOONA, aceptar solo una plataforma de la lista permitida y activar su pestaña existente ante el clic explícito. Si faltara la extensión o la pestaña, el enlace normal serviría como respaldo. La versión 0.3 mantiene esa interfaz externa fuera del manifiesto. [Mensajería entre páginas y extensiones de Chrome](https://developer.chrome.com/docs/extensions/develop/concepts/messaging)

## Formatos y límites por plataforma

Los formatos de la tabla son casos que acepta el parser. Son adaptadores conservadores y no representan una garantía de que el sitio los produzca en una cuenta, región o versión concreta.

| Plataforma | Host autorizado | Formatos de ejemplo y límites |
| --- | --- | --- |
| Instagram | `www.instagram.com` | `(N) Instagram` o `Instagram (N)`. Un título con el nombre de un perfil o solo la marca queda como desconocido. La actividad de la cuenta puede existir sin indicador en el título. |
| Facebook | `www.facebook.com` | `(N) Facebook` o `Facebook (N)`. Quedan fuera las páginas con nombre de grupo, persona o página, y Messenger en un host distinto. El título por sí solo no distingue avisos de mensajes. |
| WhatsApp Web | `web.whatsapp.com` | `(N) WhatsApp`, `WhatsApp (N)` y las mismas variantes con `WhatsApp Web`. Un título sin cifra o con texto adicional queda como desconocido. La cifra por sí sola no permite distinguir chats pendientes de mensajes individuales. |
| LinkedIn | `www.linkedin.com` | Indicador delante o detrás de `LinkedIn`, `Feed \| LinkedIn` o `Inicio \| LinkedIn`. Se omiten otros títulos de navegación y otros idiomas del prefijo de sección. El título no permite separar mensajes, avisos o invitaciones. |

`(N+)` se muestra como límite inferior. Solo se muestra cero cuando el título incluye explícitamente `(0)`. Si hay varias pestañas del mismo sitio, todas deben dar el mismo indicador interpretable para mostrarlo una sola vez. Las diferencias, los títulos ausentes y los formatos no reconocidos quedan como desconocidos. El significado de la cifra depende de la plataforma.

En el perfil real se observaron Instagram **3** y WhatsApp Web **1** en pruebas separadas. Facebook y LinkedIn devolvieron **desconocido** con permisos concedidos. Esas cifras son observaciones de la fase anterior y no se usan como valores iniciales.

## Comunicación local con MOONA

Chrome inicia el host de Windows por demanda con `runtime.sendNativeMessage` y usa sus flujos binarios estándar. Chrome y el host validan el único ID configurado en `allowed_origins`. El mensaje contiene una instantánea con cuatro campos por plataforma, `platform`, `value`, `state` y `updated_at` (UTC). El host valida el tamaño, los campos y sus valores antes de guardar una sola instantánea en `%LOCALAPPDATA%\MOONA\Connect\indicators.db`. El host conserva la observación más reciente ante escrituras concurrentes. La comunicación no abre puertos ni envía datos a Groq, Gemini u otros servidores. [Documentación de Native Messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)

Configura un solo perfil de Chrome para el piloto. Dos perfiles con el mismo ID compartirían la misma instantánea de Windows. El lector del Social Hub consulta la base cada cinco segundos mientras la sesión de MOONA está activa. Outlook queda fuera de la extensión.

| Estado que muestra MOONA | Significado |
| --- | --- |
| Número o `N+` | Indicador explícito observado en el título. |
| Desconocido | Hay una pestaña detectable sin cifra interpretable o hay resultados contradictorios. |
| Sin pestaña | No queda una pestaña detectable del host autorizado. |
| Sin permiso | El acceso a ese sitio está pendiente o se revocó. |
| No disponible | Chrome no pudo completar la consulta de esa plataforma. |
| Desactualizado | Han pasado al menos dos minutos desde la última instantánea. |
| Sin conexión | Aún no existe una instantánea válida o han pasado cinco minutos desde la última. |

El panel de Chrome informa de inmediato si el host responde al pulsar **Actualizar**. MOONA estima la conexión por la antigüedad de la última instantánea válida, para tolerar pausas y retrasos de Chrome. Las cifras antiguas se ocultan y la fecha UTC sigue disponible en el detalle del indicador.

## Instalar el host en Windows

Desde la raíz del repositorio, en PowerShell y con el entorno Python de trabajo activo:

```powershell
python -m pip install -r requirements.txt
python -m pip install PyInstaller
python -m PyInstaller --noconfirm --onedir --console --name moona-connect-host --paths . --distpath .moona-connect-build/dist --workpath .moona-connect-build/work --specpath .moona-connect-build experiments/moona_connect_host/native_host.py
```

1. Carga o recarga la extensión en `chrome://extensions`. Si Chrome la desactiva al detectar permisos nuevos, revisa el aviso y vuelve a habilitarla. Copia el ID de 32 letras de esa instalación de **MOONA Connect**.
2. Ejecuta el registro del host con el ID copiado. El script solicita confirmación antes de modificar `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.moona.connect`. Puedes añadir `-WhatIf` para previsualizar la operación.

```powershell
.\experiments\moona_connect_host\manage_native_host.ps1 -Action Install -ExtensionId 'ID_COPIADO_DE_CHROME'
```

3. Mantén la carpeta generada `.moona-connect-build\dist\moona-connect-host\` en la misma ubicación, junto con su subcarpeta `_internal`. Si mueves el repositorio o cambia el ID de la extensión, vuelve a ejecutar la instalación con el ID correcto.
4. Inicia MOONA como el mismo usuario de Windows y limita la interfaz a este equipo con `python -m streamlit run app.py --server.address 127.0.0.1`. Abre MOONA en `http://localhost:8501`.

## Validar la integración manualmente

1. Pulsa **Actualizar** en Chrome. Espera **MOONA conectado** y verifica que el Social Hub refleje el resultado en unos segundos.
2. Con el panel de Chrome cerrado, cambia una cifra real o cierra la última pestaña autorizada de una plataforma. Comprueba que MOONA se actualice automáticamente. Un título que carezca de cifra válida debe mostrar **Desconocido**.
3. Deshabilita temporalmente la extensión. Después de dos minutos desde la última actualización debe aparecer **Desactualizado**, y a los cinco minutos **Sin conexión**. Reactívala y pulsa **Actualizar** para recuperar la conexión.
4. Cambia el idioma en MOONA para comprobar los mismos estados en inglés. El panel de la extensión usa el idioma de Chrome y el español como idioma de respaldo.
5. Con **Monitoreo automático** desactivado, reinicia Chrome sin pestañas de las plataformas y verifica que no se abra ninguna. Abre de forma manual un único sitio autorizado, deja otro autorizado cerrado y vuelve al panel. Activa el monitoreo. Verifica que solo aparezca la pestaña que faltaba y que la pestaña activa siga seleccionada. Reinicia Chrome para comprobar que se conserva el consentimiento y que las pestañas ya restauradas no se duplican en condiciones normales.
6. Cierra una pestaña monitoreada y confirma **Sin pestaña** en MOONA. Comprueba que sigue cerrada tras la siguiente alarma. Si Chrome permite descartarla desde `chrome://discards`, prueba también con una pestaña de prueba y comprueba **Desconocido**. Por último, desactiva el monitoreo y reinicia el perfil sin esas pestañas para comprobar que no se vuelven a abrir.

## Desinstalar el host

Deshabilita primero MOONA Connect en Chrome. Ejecuta el siguiente comando y confirma el cambio en el registro. El script elimina la entrada del usuario, el manifiesto y la instantánea local de esta integración. Después puedes retirar la extensión desde `chrome://extensions` y borrar la carpeta de compilación `.moona-connect-build`.

```powershell
.\experiments\moona_connect_host\manage_native_host.ps1 -Action Uninstall
```

## Pruebas automatizadas

Desde la raíz del repositorio, con Python y Node.js:

```powershell
node --test experiments/moona_connect/*.test.mjs
python -m unittest experiments.moona_connect_host.test_native_host -v
```

Las pruebas cubren el parser, los eventos automáticos y manuales, el protocolo binario, el rechazo de orígenes y campos extra, la persistencia y la vista bilingüe. Para ejecutar las pruebas de Python contra el binario compilado, configura `MOONA_TEST_HOST_EXE` con su ruta absoluta. Las pruebas usan almacenamiento temporal y no modifican el registro.

En Chrome 157.0.8103.79, un perfil temporal con dos permisos preconcedidos y sin acceso a los sitios confirmó el estado inicial apagado, la apertura de dos pestañas inactivas sin cambiar la activa, la desactivación sin cerrar pestañas y la ausencia de duplicados al reactivar. El reinicio con restauración de sesión y los indicadores de cuentas reales se comprueban con los pasos manuales.

[Permisos opcionales en Chrome](https://developer.chrome.com/docs/extensions/reference/api/permissions) · [API de pestañas](https://developer.chrome.com/docs/extensions/reference/api/tabs) · [Carga de extensiones descomprimidas](https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world)
