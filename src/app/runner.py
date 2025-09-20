from src.app.logging import setup_logger


def main() -> None:
    logger = setup_logger()
    logger.info("ETHID project bootstrap started successfully!")
    logger.info("Next steps: подключение WebSocket и расчёты.")


if __name__ == "__main__":
    main()
