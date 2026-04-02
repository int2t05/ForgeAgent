# -*- coding: utf-8 -*-
"""
Calculator with basic arithmetic operations and self-contained tests.
No external dependencies required.
"""

from __future__ import annotations
import math
import sys


def add(a, b):
    """Return sum of a and b."""
    return a + b


def subtract(a, b):
    """Return a minus b."""
    return a - b


def multiply(a, b):
    """Return product of a and b."""
    return a * b


def divide(a, b):
    """Return a divided by b. Raises ZeroDivisionError if b is 0."""
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return a / b


def power(a, b):
    """Return a raised to the power of b (a^b)."""
    return a ** b


def modulo(a, b):
    """Return remainder of a divided by b. Raises ZeroDivisionError if b is 0."""
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return a % b


def absolute(a):
    """Return absolute value of a."""
    return abs(a)


def square_root(a):
    """Return square root of a. Raises ValueError if a is negative."""
    if a < 0:
        raise ValueError("cannot compute square root of negative number")
    return math.sqrt(a)


def run_tests():
    """Run all test cases with assert statements."""
    tests_passed = 0
    tests_failed = 0

    # Test add function
    try:
        assert add(2, 3) == 5, "add(2, 3) should be 5"
        assert add(-1, 1) == 0, "add(-1, 1) should be 0"
        assert add(0, 0) == 0, "add(0, 0) should be 0"
        assert add(-5, -3) == -8, "add(-5, -3) should be -8"
        print("[PASS] add tests")
        tests_passed += 1
    except AssertionError as e:
        print("[FAIL] add: " + str(e))
        tests_failed += 1

    # Test subtract function
    try:
        assert subtract(10, 4) == 6, "subtract(10, 4) should be 6"
        assert subtract(5, 5) == 0, "subtract(5, 5) should be 0"
        assert subtract(-2, 3) == -5, "subtract(-2, 3) should be -5"
        assert subtract(0, 5) == -5, "subtract(0, 5) should be -5"
        print("[PASS] subtract tests")
        tests_passed += 1
    except AssertionError as e:
        print("[FAIL] subtract: " + str(e))
        tests_failed += 1

    # Test multiply function
    try:
        assert multiply(3, 4) == 12, "multiply(3, 4) should be 12"
        assert multiply(-2, 5) == -10, "multiply(-2, 5) should be -10"
        assert multiply(0, 100) == 0, "multiply(0, 100) should be 0"
        assert multiply(-3, -3) == 9, "multiply(-3, -3) should be 9"
        print("[PASS] multiply tests")
        tests_passed += 1
    except AssertionError as e:
        print("[FAIL] multiply: " + str(e))
        tests_failed += 1

    # Test divide function
    try:
        assert divide(10, 2) == 5.0, "divide(10, 2) should be 5.0"
        assert divide(9, 3) == 3.0, "divide(9, 3) should be 3.0"
        assert divide(7, 2) == 3.5, "divide(7, 2) should be 3.5"
        assert divide(-6, 2) == -3.0, "divide(-6, 2) should be -3.0"
        print("[PASS] divide tests")
        tests_passed += 1
    except AssertionError as e:
        print("[FAIL] divide: " + str(e))
        tests_failed += 1

    # Test divide by zero
    try:
        divide(5, 0)
        print("[FAIL] divide by zero should raise ZeroDivisionError")
        tests_failed += 1
    except ZeroDivisionError:
        print("[PASS] divide by zero raises ZeroDivisionError")
        tests_passed += 1

    # Test power function
    try:
        assert power(2, 3) == 8, "power(2, 3) should be 8"
        assert power(5, 0) == 1, "power(5, 0) should be 1"
        assert power(3, 2) == 9, "power(3, 2) should be 9"
        assert power(-2, 3) == -8, "power(-2, 3) should be -8"
        assert power(4, 0.5) == 2.0, "power(4, 0.5) should be 2.0"
        print("[PASS] power tests")
        tests_passed += 1
    except AssertionError as e:
        print("[FAIL] power: " + str(e))
        tests_failed += 1

    # Test modulo function
    try:
        assert modulo(10, 3) == 1, "modulo(10, 3) should be 1"
        assert modulo(15, 5) == 0, "modulo(15, 5) should be 0"
        assert modulo(-7, 3) == -1, "modulo(-7, 3) should be -1"
        assert modulo(5, 2) == 1, "modulo(5, 2) should be 1"
        print("[PASS] modulo tests")
        tests_passed += 1
    except AssertionError as e:
        print("[FAIL] modulo: " + str(e))
        tests_failed += 1

    # Test modulo by zero
    try:
        modulo(5, 0)
        print("[FAIL] modulo by zero should raise ZeroDivisionError")
        tests_failed += 1
    except ZeroDivisionError:
        print("[PASS] modulo by zero raises ZeroDivisionError")
        tests_passed += 1

    # Test absolute function
    try:
        assert absolute(5) == 5, "absolute(5) should be 5"
        assert absolute(-5) == 5, "absolute(-5) should be 5"
        assert absolute(0) == 0, "absolute(0) should be 0"
        assert absolute(-100) == 100, "absolute(-100) should be 100"
        print("[PASS] absolute tests")
        tests_passed += 1
    except AssertionError as e:
        print("[FAIL] absolute: " + str(e))
        tests_failed += 1

    # Test square_root function
    try:
        assert square_root(16) == 4.0, "square_root(16) should be 4.0"
        assert square_root(9) == 3.0, "square_root(9) should be 3.0"
        assert square_root(2) == math.sqrt(2), "square_root(2) should be sqrt(2)"
        assert square_root(0) == 0.0, "square_root(0) should be 0.0"
        print("[PASS] square_root tests")
        tests_passed += 1
    except AssertionError as e:
        print("[FAIL] square_root: " + str(e))
        tests_failed += 1

    # Test square_root of negative number
    try:
        square_root(-4)
        print("[FAIL] square_root of negative should raise ValueError")
        tests_failed += 1
    except ValueError:
        print("[PASS] square_root of negative raises ValueError")
        tests_passed += 1

    # Summary
    sep = "=" * 40
    print("")
    print(sep)
    print("SUMMARY: " + str(tests_passed) + " passed, " + str(tests_failed) + " failed")
    print(sep)

    return tests_failed == 0


if __name__ == "__main__":
    print("Running calculator tests...")
    sep = "=" * 40
    print("")
    print(sep)
    success = run_tests()
    sys.exit(0 if success else 1)
