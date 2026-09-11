"""JX password codec compatible with jxoffline/OnlineGMPassTool.

Derived from https://github.com/jxoffline/jxtools under the MIT License.
The 32-character result is reversible compatibility encoding, not a secure hash.
"""

from __future__ import annotations

import secrets


RESULT_LENGTH = 32
MAX_PASSWORD_LENGTH = 20
MIN_KEY_LENGTH = 10
PKEY_MASK = 151
PKEY_OFFSET = 7
MIN_CHAR = 0x20
MAX_CHAR = 0x7E
CHAR_COUNT = MAX_CHAR - MIN_CHAR + 1
PRIMES = (
    1153, 1789, 2797, 3023, 3491, 3617, 4519, 4547,
    5261, 5939, 6449, 7307, 8053, 9221, 9719, 9851,
    313, 659, 1229, 1847, 2459, 3121, 3793, 4483,
    5179, 6121, 6833, 7333, 7829, 8353, 9323, 9829,
)


def _valid_char(character):
    return character == "_" or character.isascii() and character.isalnum()


def _char_to_int(character):
    value = ord(character) ^ PKEY_MASK
    value = (value << PKEY_OFFSET) | (value >> (8 - PKEY_OFFSET))
    return value & 0x1F


def _int_to_char(value, seed):
    if not 0 <= value <= RESULT_LENGTH - 2:
        raise ValueError("Giá trị mã hóa JX không hợp lệ")
    for valid_only in (True, False):
        start = seed % CHAR_COUNT
        for index in range(start, start + CHAR_COUNT):
            character = chr(index % CHAR_COUNT + MIN_CHAR)
            if _char_to_int(character) == value and (not valid_only or _valid_char(character)):
                return character
    raise ValueError("Không tạo được ký tự mã hóa JX")


def _swap(characters):
    for left, right in ((0, 13), (31, 25), (12, 30), (7, 19), (3, 21), (9, 20), (15, 18)):
        characters[left], characters[right] = characters[right], characters[left]


def decrypt_password(encoded):
    if not isinstance(encoded, str) or len(encoded) != RESULT_LENGTH:
        raise ValueError("Chuỗi mã hóa JX phải dài 32 ký tự")
    buffer = list(encoded)
    _swap(buffer)
    key_length = _char_to_int(buffer[0])
    if not MIN_KEY_LENGTH <= key_length <= RESULT_LENGTH - 2:
        raise ValueError("Khóa mã hóa JX không hợp lệ")
    password_length = _char_to_int(buffer[key_length + 1])
    if not 0 <= password_length <= MAX_PASSWORD_LENGTH:
        raise ValueError("Độ dài mật khẩu JX không hợp lệ")
    key = buffer[1:key_length + 1]
    encrypted = buffer[key_length + 2:key_length + 2 + password_length]
    return "".join(
        chr((CHAR_COUNT + ord(encrypted[index]) - MIN_CHAR - (ord(key[index % key_length]) - MIN_CHAR))
            % CHAR_COUNT + MIN_CHAR)
        for index in range(password_length)
    )


def encrypt_password(password):
    if not isinstance(password, str) or not 1 <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError("Mật khẩu JX phải dài từ 1 đến 20 ký tự")
    if any(not MIN_CHAR <= ord(character) <= MAX_CHAR for character in password):
        raise ValueError("Mật khẩu JX chỉ hỗ trợ ký tự ASCII hiển thị")

    for _attempt in range(32):
        seed = secrets.randbits(31)
        password_length = len(password)
        key_length = RESULT_LENGTH - password_length - 2
        if key_length > MIN_KEY_LENGTH:
            key_length = (seed + 10237) % (key_length - MIN_KEY_LENGTH) + MIN_KEY_LENGTH
        result = [""] * RESULT_LENGTH
        result[0] = _int_to_char(key_length, seed)
        key = []
        for index in range(key_length):
            random_value = seed + PRIMES[index]
            character = chr(random_value % CHAR_COUNT + MIN_CHAR)
            if not _valid_char(character):
                character = chr((ord("a") if random_value & 1 else ord("A")) + random_value % 26)
            key.append(character)
        encrypted = []
        ok = True
        for index, source in enumerate(password):
            key_character = key[index % key_length]
            value = chr(((ord(source) - MIN_CHAR + ord(key_character) - MIN_CHAR) % CHAR_COUNT) + MIN_CHAR)
            attempts = 0
            while not _valid_char(key_character) or not _valid_char(value):
                value = chr(MIN_CHAR if ord(value) + 1 > MAX_CHAR else ord(value) + 1)
                key_character = chr(MIN_CHAR if ord(key_character) + 1 > MAX_CHAR else ord(key_character) + 1)
                key[index % key_length] = key_character
                attempts += 1
                if attempts > 255:
                    ok = False
                    break
            if not ok:
                break
            encrypted.append(value)
        if not ok:
            continue
        result[1:key_length + 1] = key
        result[key_length + 1] = _int_to_char(password_length, seed)
        result[key_length + 2:key_length + 2 + password_length] = encrypted
        for index in range(RESULT_LENGTH - 2 - key_length - password_length):
            random_value = seed + PRIMES[RESULT_LENGTH - index - 1]
            character = chr(random_value % CHAR_COUNT + MIN_CHAR)
            if not _valid_char(character):
                character = chr((ord("a") if random_value & 1 else ord("A")) + random_value % 26)
            result[RESULT_LENGTH - index - 1] = character
        _swap(result)
        encoded = "".join(result)
        if decrypt_password(encoded) == password:
            return encoded
    raise RuntimeError("Không tạo được chuỗi mật khẩu JX hợp lệ")
