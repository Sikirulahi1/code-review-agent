import sys
import secrets
import string

ALPHABET = string.ascii_letters + string.digits


def generate_random_key(length: int = 32) -> str:
    if length < 1:
        raise ValueError("length must be at least 1")

    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def main() -> None:
    length = int(sys.argv[1]) if len(sys.argv) > 1 else 32
    print(generate_random_key(length))


if __name__ == "__main__":
    main()
