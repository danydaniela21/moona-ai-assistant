"""Consulta puntual de toasts de Windows mediante WinRT, solo con metadatos.

Instalar winrt-Windows.UI.Notifications.Management, winrt-Windows.UI.Notifications
y winrt-Windows.ApplicationModel en un entorno Python independiente.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from collections.abc import Sequence


PLATFORMS = ("instagram", "facebook", "whatsapp", "linkedin", "outlook")


async def inspect_notifications(app_ids: dict[str, str]) -> dict[str, object]:
    from winrt.windows.applicationmodel import AppInfo
    from winrt.windows.ui.notifications import NotificationKinds
    from winrt.windows.ui.notifications.management import (
        UserNotificationListener,
        UserNotificationListenerAccessStatus,
    )

    listener = UserNotificationListener.current
    status = listener.get_access_status()
    if status != UserNotificationListenerAccessStatus.ALLOWED:
        return {"access": status.name.lower()}

    notifications = await asyncio.wait_for(
        listener.get_notifications_async(NotificationKinds.TOAST), timeout=10
    )
    # Windows puede devolver una lista vacía si se revoca el permiso durante la consulta.
    status = listener.get_access_status()
    if status != UserNotificationListenerAccessStatus.ALLOWED:
        return {"access": status.name.lower()}

    counts: Counter[str] = Counter()
    unclassified = 0
    for notification in notifications:
        try:
            # Solo se consulta el AUMID. No se accede a notification.notification.
            app_info: AppInfo = notification.app_info
            app_id = app_info.app_user_model_id
        except (AttributeError, OSError):
            unclassified += 1
            continue
        platform = app_ids.get(app_id.casefold()) if app_id else None
        if platform is None:
            unclassified += 1
        else:
            counts[platform] += 1

    return {
        "access": "allowed",
        "available_windows_toasts": len(notifications),
        "observed_by_platform": dict(counts),
        "unclassified_windows_toasts": unclassified,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app-id",
        action="append",
        default=[],
        metavar="PLATFORM=AUMID",
        help=(
            f"Mapeo exacto de una fuente dedicada ({', '.join(PLATFORMS)}). "
            "Repetible. Excluye identificadores de navegadores y de aplicaciones compartidas."
        ),
    )
    args = parser.parse_args(argv)
    app_ids: dict[str, str] = {}
    for value in args.app_id:
        platform, _, app_id = value.partition("=")
        app_id = app_id.strip().casefold()
        if platform not in PLATFORMS or not app_id:
            parser.error("--app-id requiere PLATFORM=AUMID con una plataforma válida")
        if app_id == "chrome":
            parser.error("El AUMID compartido de Chrome no identifica un sitio web")
        if app_id in app_ids and app_ids[app_id] != platform:
            parser.error("Un mismo AUMID no se puede asociar a varias plataformas")
        app_ids[app_id] = platform

    if sys.platform != "win32":
        parser.exit(1, "La prueba requiere Windows.\n")

    try:
        result = asyncio.run(inspect_notifications(app_ids))
    except ImportError:
        parser.exit(1, "Instala las tres proyecciones de PyWinRT indicadas en --help.\n")
    except (OSError, TimeoutError) as exc:
        hresult = getattr(exc, "winerror", None)
        print(json.dumps({"error": type(exc).__name__, "hresult": hresult}))
        return 1

    print(json.dumps(result, indent=2))
    return 0 if result["access"] == "allowed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
