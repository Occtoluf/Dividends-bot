from aiogram import Router

from src.bot.handlers import alias_pick, coupons, dividends, totals


def build_router() -> Router:
    router = Router(name="root")
    router.include_router(dividends.router)
    router.include_router(coupons.router)
    router.include_router(totals.router)
    router.include_router(alias_pick.router)
    return router
