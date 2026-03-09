from loguru import logger
import requests

SERVER_URL = "http://127.0.0.1:8000/status"


def check_my_light(city, street, house) -> None:
    params = {"city": city, "street": street, "house": house}
    response = requests.get(SERVER_URL, params=params)
    logger.info(f"Request to server: {response.url}")
    logger.info(f"city: {city}, street: {street}, house: {house}")

    if response.status_code == 200:
        data = response.json()
        logger.info(f"🏠 Address: {data.get('address', f'{city}, {street}, {house}')}")
        logger.info(f"💡 Status: {data.get('message', data)}")
    else:
        logger.error("Error while requesting the server")


def main():
    """Entry point for the dtek-client command."""
    # Example call with user input
    user_input = input("Enter your address (city, street, house) [Odesa, Nebesnoi Sotni Ave, 79B]: ")
    if user_input.strip():
        try:
            city, street, house = user_input.split(", ")
        except ValueError:
            logger.error("Invalid format. Expected: city, street, house")
            return
    else:
        # Default values if user provides empty input
        city, street, house = "Odesa", "Nebesnoi Sotni Ave", "79B"

    logger.info(check_my_light(city, street, house))


if __name__ == "__main__":
    main()
