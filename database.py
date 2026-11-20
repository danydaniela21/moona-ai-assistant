"""Persistencia local de tareas de JARVIS mediante SQLite."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator


CATEGORIAS = ("Personal", "Académica", "Profesional")
PRIORIDADES = ("Alta", "Media", "Baja")
ESTADOS = ("Pendiente", "En progreso", "Completada")


class DatabaseError(Exception):
    """Error controlado de acceso o validación de la base de datos."""


class TaskDatabase:
    """Encapsula las operaciones CRUD de tareas en una base SQLite local."""

    _CAMPOS_EDITABLES = {
        "titulo",
        "descripcion",
        "fecha_vencimiento",
        "prioridad",
        "categoria",
        "estado",
    }

    def __init__(self, database_path: str | Path = "jarvis_tasks.db") -> None:
        self.database_path = Path(database_path)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Abre una conexión configurada y garantiza su cierre."""
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self.database_path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        except sqlite3.Error as exc:
            raise DatabaseError("No fue posible acceder a la base de datos local.") from exc
        finally:
            if connection is not None:
                connection.close()

    def initialize(self) -> None:
        """Crea la tabla y los índices si todavía no existen."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    titulo TEXT NOT NULL CHECK(length(trim(titulo)) > 0),
                    descripcion TEXT,
                    fecha_vencimiento TEXT NOT NULL,
                    prioridad TEXT NOT NULL
                        CHECK(prioridad IN ('Alta', 'Media', 'Baja')),
                    categoria TEXT NOT NULL
                        CHECK(categoria IN ('Personal', 'Académica', 'Profesional')),
                    estado TEXT NOT NULL DEFAULT 'Pendiente'
                        CHECK(estado IN ('Pendiente', 'En progreso', 'Completada')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_estado ON tasks(estado);
                CREATE INDEX IF NOT EXISTS idx_tasks_categoria ON tasks(categoria);
                CREATE INDEX IF NOT EXISTS idx_tasks_prioridad ON tasks(prioridad);
                CREATE INDEX IF NOT EXISTS idx_tasks_vencimiento
                    ON tasks(fecha_vencimiento);
                """
            )

    @staticmethod
    def _normalize_date(value: str | date) -> str:
        """Valida una fecha y devuelve su representación ISO YYYY-MM-DD."""
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            try:
                return date.fromisoformat(value).isoformat()
            except ValueError as exc:
                raise DatabaseError("La fecha de vencimiento no es válida.") from exc
        raise DatabaseError("La fecha de vencimiento debe ser una fecha ISO.")

    @staticmethod
    def _validate_choice(name: str, value: str, allowed: tuple[str, ...]) -> str:
        if value not in allowed:
            raise DatabaseError(
                f"{name.capitalize()} no válido. Opciones: {', '.join(allowed)}."
            )
        return value

    @staticmethod
    def _normalize_title(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DatabaseError("El título de la tarea es obligatorio.")
        return value.strip()

    @staticmethod
    def _normalize_description(value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise DatabaseError("La descripción debe ser texto.")
        return value.strip() or None

    def create_task(
        self,
        titulo: str,
        fecha_vencimiento: str | date,
        prioridad: str,
        categoria: str,
        descripcion: str | None = None,
        estado: str = "Pendiente",
    ) -> int:
        """Crea una tarea y devuelve su identificador."""
        values = (
            self._normalize_title(titulo),
            self._normalize_description(descripcion),
            self._normalize_date(fecha_vencimiento),
            self._validate_choice("prioridad", prioridad, PRIORIDADES),
            self._validate_choice("categoría", categoria, CATEGORIAS),
            self._validate_choice("estado", estado, ESTADOS),
        )
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tasks (
                    titulo, descripcion, fecha_vencimiento, prioridad,
                    categoria, estado, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*values, now, now),
            )
            return int(cursor.lastrowid)

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        """Obtiene una tarea por identificador."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_tasks(
        self,
        categoria: str | None = None,
        prioridad: str | None = None,
        estado: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lista tareas, aplicando opcionalmente filtros combinables."""
        conditions: list[str] = []
        parameters: list[str] = []
        filters = (
            ("categoria", categoria, CATEGORIAS),
            ("prioridad", prioridad, PRIORIDADES),
            ("estado", estado, ESTADOS),
        )
        for column, value, allowed in filters:
            if value is not None:
                self._validate_choice(column, value, allowed)
                conditions.append(f"{column} = ?")
                parameters.append(value)

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = (
            "SELECT * FROM tasks"
            + where_clause
            + " ORDER BY fecha_vencimiento ASC, id DESC"
        )
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def update_task(self, task_id: int, **changes: Any) -> bool:
        """Actualiza uno o varios campos permitidos de una tarea existente."""
        unknown = set(changes) - self._CAMPOS_EDITABLES
        if unknown:
            raise DatabaseError(f"Campos no editables: {', '.join(sorted(unknown))}.")
        if not changes:
            raise DatabaseError("No se proporcionaron cambios para la tarea.")

        normalized: dict[str, Any] = {}
        for field, value in changes.items():
            if field == "titulo":
                value = self._normalize_title(value)
            elif field == "descripcion":
                value = self._normalize_description(value)
            elif field == "fecha_vencimiento":
                value = self._normalize_date(value)
            elif field == "prioridad":
                value = self._validate_choice(field, value, PRIORIDADES)
            elif field == "categoria":
                value = self._validate_choice(field, value, CATEGORIAS)
            elif field == "estado":
                value = self._validate_choice(field, value, ESTADOS)
            normalized[field] = value

        normalized["updated_at"] = datetime.now().astimezone().isoformat(
            timespec="seconds"
        )
        assignments = ", ".join(f"{field} = ?" for field in normalized)
        parameters = [*normalized.values(), task_id]
        with self._connection() as connection:
            cursor = connection.execute(
                f"UPDATE tasks SET {assignments} WHERE id = ?", parameters
            )
            return cursor.rowcount > 0

    def delete_task(self, task_id: int) -> bool:
        """Elimina definitivamente una tarea por identificador."""
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            return cursor.rowcount > 0

    def count_by_status(self) -> dict[str, int]:
        """Devuelve el total para cada estado, incluidos los que tienen cero."""
        counts = {status: 0 for status in ESTADOS}
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT estado, COUNT(*) AS total FROM tasks GROUP BY estado"
            ).fetchall()
        counts.update({row["estado"]: int(row["total"]) for row in rows})
        return counts


# Alias descriptivos para facilitar el consumo desde la interfaz.
Database = TaskDatabase
