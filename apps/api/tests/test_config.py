from app.core.config import Settings


def test_plain_postgres_scheme_gets_asyncpg_dialect() -> None:
    """Managed Postgres providers (Render, Heroku-style, Railway) hand out
    postgres:// or postgresql:// -- this app's async engine needs the
    +asyncpg dialect explicit or it falls back to a driver that isn't
    installed here."""
    assert (
        Settings(database_url="postgres://user:pass@host:5432/db").database_url
        == "postgresql+asyncpg://user:pass@host:5432/db"
    )
    assert (
        Settings(database_url="postgresql://user:pass@host:5432/db").database_url
        == "postgresql+asyncpg://user:pass@host:5432/db"
    )


def test_already_correct_dialect_is_left_alone() -> None:
    url = "postgresql+asyncpg://user:pass@host:5432/db"
    assert Settings(database_url=url).database_url == url


def test_sqlite_url_is_untouched() -> None:
    url = "sqlite+aiosqlite:///./data/notamsys.db"
    assert Settings(database_url=url).database_url == url


def test_libpq_sslmode_is_translated_for_asyncpg() -> None:
    """asyncpg's connect() doesn't recognize the libpq-style sslmode
    parameter Neon/Supabase/etc. connection strings default to -- confirmed
    live against a real Neon database: passing it through raises
    "unexpected keyword argument 'sslmode'" and the app never starts."""
    url = "postgresql://user:pass@host/db?sslmode=require"
    assert Settings(database_url=url).database_url == "postgresql+asyncpg://user:pass@host/db?ssl=require"


def test_channel_binding_param_is_dropped() -> None:
    """channel_binding has no asyncpg equivalent -- dropped rather than
    guessed at, same reasoning as sslmode above."""
    url = "postgresql://user:pass@host/db?sslmode=require&channel_binding=require"
    assert Settings(database_url=url).database_url == "postgresql+asyncpg://user:pass@host/db?ssl=require"
