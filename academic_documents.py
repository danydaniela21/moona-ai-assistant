"""Persistencia y extracción local de documentos académicos de JARVIS."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from docx import Document
from openpyxl import load_workbook


ESTADOS_EVALUACION = ("Pendiente", "En revisión", "Evaluada")
EXTENSIONES_PERMITIDAS = {".docx", ".xlsx"}
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_EXTRACTED_CHARS = 50_000


class AcademicDocumentError(Exception):
    """Error controlado del repositorio de documentos académicos."""


def _limitar_texto(texto: str) -> str:
    """Normaliza y limita la extracción almacenada localmente."""

    limpio = "\n".join(linea.strip() for linea in texto.splitlines() if linea.strip())
    return limpio[:MAX_EXTRACTED_CHARS]


def extract_docx(file_bytes: bytes) -> str:
    """Extrae párrafos y tablas de un archivo Word en memoria."""

    try:
        document = Document(BytesIO(file_bytes))
        partes = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                valores = [cell.text.strip() for cell in row.cells]
                if any(valores):
                    partes.append(" | ".join(valores))
        return _limitar_texto("\n".join(partes))
    except Exception as exc:
        raise AcademicDocumentError("El archivo Word no es válido o está dañado.") from exc


def extract_xlsx(file_bytes: bytes) -> str:
    """Extrae valores calculados visibles de todas las hojas de Excel."""

    workbook = None
    try:
        workbook = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
        partes: list[str] = []
        for sheet in workbook.worksheets:
            partes.append(f"Hoja: {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                valores = [str(value).strip() if value is not None else "" for value in row]
                if any(valores):
                    partes.append(" | ".join(valores))
                if sum(len(parte) for parte in partes) >= MAX_EXTRACTED_CHARS:
                    return _limitar_texto("\n".join(partes))
        return _limitar_texto("\n".join(partes))
    except Exception as exc:
        raise AcademicDocumentError("El archivo Excel no es válido o está dañado.") from exc
    finally:
        if workbook is not None:
            workbook.close()


class AcademicDocumentRepository:
    """Gestiona metadatos SQLite y archivos locales con nombres no predecibles."""

    def __init__(self, database_path: str | Path, storage_dir: str | Path) -> None:
        self.database_path = Path(database_path)
        self.storage_dir = Path(storage_dir)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self.database_path)
            connection.row_factory = sqlite3.Row
            with connection:
                yield connection
        except sqlite3.Error as exc:
            raise AcademicDocumentError("No fue posible acceder a los documentos locales.") from exc
        finally:
            if connection is not None:
                connection.close()

    def initialize(self) -> None:
        """Crea el almacenamiento local y su tabla si no existen."""

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS academic_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_name TEXT NOT NULL,
                    stored_name TEXT NOT NULL UNIQUE,
                    extension TEXT NOT NULL CHECK(extension IN ('.docx', '.xlsx')),
                    subject TEXT NOT NULL,
                    activity TEXT NOT NULL,
                    evaluation_status TEXT NOT NULL,
                    grade TEXT,
                    extracted_text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_academic_documents_created
                    ON academic_documents(created_at DESC);
                """
            )

    @staticmethod
    def _required(value: str, label: str) -> str:
        result = value.strip() if isinstance(value, str) else ""
        if not result:
            raise AcademicDocumentError(f"{label} es obligatorio.")
        return result

    def add(
        self,
        *,
        original_name: str,
        file_bytes: bytes,
        subject: str,
        activity: str,
        evaluation_status: str,
        grade: str | None = None,
    ) -> int:
        """Valida, extrae y guarda un documento de manera local."""

        extension = Path(original_name).suffix.lower()
        if extension not in EXTENSIONES_PERMITIDAS:
            raise AcademicDocumentError("Solo se permiten archivos .docx y .xlsx.")
        if not file_bytes or len(file_bytes) > MAX_FILE_SIZE:
            raise AcademicDocumentError("El archivo debe contener datos y no superar 10 MB.")
        if evaluation_status not in ESTADOS_EVALUACION:
            raise AcademicDocumentError("El estado de evaluación no es válido.")

        extracted = extract_docx(file_bytes) if extension == ".docx" else extract_xlsx(file_bytes)
        if not extracted:
            raise AcademicDocumentError("El documento no contiene texto o valores procesables.")

        stored_name = f"{uuid4().hex}{extension}"
        target = self.storage_dir / stored_name
        target.write_bytes(file_bytes)
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            with self._connection() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO academic_documents (
                        original_name, stored_name, extension, subject, activity,
                        evaluation_status, grade, extracted_text, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        Path(original_name).name,
                        stored_name,
                        extension,
                        self._required(subject, "La asignatura"),
                        self._required(activity, "La actividad"),
                        evaluation_status,
                        grade.strip() if isinstance(grade, str) and grade.strip() else None,
                        extracted,
                        now,
                    ),
                )
                return int(cursor.lastrowid)
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def list(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Lista documentos recientes sin cargar sus contenidos binarios."""

        query = "SELECT * FROM academic_documents ORDER BY created_at DESC, id DESC"
        parameters: tuple[int, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            parameters = (max(1, int(limit)),)
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def get(self, document_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM academic_documents WHERE id = ?", (document_id,)
            ).fetchone()
        return dict(row) if row else None

    def read_file(self, document_id: int) -> bytes:
        """Lee un archivo registrado sin aceptar rutas proporcionadas por el usuario."""

        document = self.get(document_id)
        if not document:
            raise AcademicDocumentError("El documento solicitado no existe.")
        path = self.storage_dir / str(document["stored_name"])
        try:
            return path.read_bytes()
        except OSError as exc:
            raise AcademicDocumentError("El archivo local no está disponible.") from exc

    def delete(self, document_id: int) -> bool:
        """Elimina el registro y su archivo local asociado."""

        document = self.get(document_id)
        if not document:
            return False
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM academic_documents WHERE id = ?", (document_id,)
            )
        if cursor.rowcount:
            (self.storage_dir / str(document["stored_name"])).unlink(missing_ok=True)
        return cursor.rowcount > 0
