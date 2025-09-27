# import asyncio
#
# import aiohttp
# import pytest
#
# from src.data.binance_ws import BinanceWsClient
#
#
# class DummyWS:
#     """Минималистичный мок ws_connect() для aiohttp: пустой поток и мгновенное завершение."""
#
#     async def __aenter__(self):
#         return self
#
#     async def __aexit__(self, exc_type, exc, tb):
#         return False  # не подавляем исключения
#
#     def __aiter__(self):
#         return self
#
#     async def __anext__(self):
#         # Сразу завершаем итерацию — сообщений нет.
#         raise StopAsyncIteration
#
#
# @pytest.mark.asyncio
# async def test_external_session_not_closed(monkeypatch):
#     # Подменяем ClientSession.ws_connect на наш DummyWS
#     def fake_ws_connect(self, *args, **kwargs):
#         return DummyWS()
#
#     monkeypatch.setattr(aiohttp.ClientSession, "ws_connect", fake_ws_connect, raising=False)
#
#     # Внешняя сессия, которую мы передаём клиенту
#     session = aiohttp.ClientSession()
#
#     client = BinanceWsClient("wss://example", ["ETHUSDT"], session=session)
#
#     # Запускаем клиент и быстро останавливаем
#     task = asyncio.create_task(client.run())
#     await asyncio.sleep(0.05)
#     await client.stop()
#     await asyncio.sleep(0.05)
#
#     if not task.done():
#         task.cancel()
#         with pytest.raises(asyncio.CancelledError):
#             await task
#
#     # КЛЮЧЕВАЯ ПРОВЕРКА: внешняя сессия не должна быть закрыта клиентом
#     assert not session.closed, "External session must not be closed by client"
#
#     await session.close()
