import argparse
from passlib.context import CryptContext


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("password", type=str)
    args = parser.parse_args()

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed_password = pwd_context.hash(args.password)
    print(hashed_password)
