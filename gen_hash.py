from werkzeug.security import generate_password_hash

password = 'ivr60psk'
hash = generate_password_hash(password)
print(f"Пароль: {password}")
print(f"Хеш:   {hash}")