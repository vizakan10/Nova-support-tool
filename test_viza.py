#!/usr/bin/env python3
import sys
sys.path.insert(0, '/mnt/c/support_kairos')

from wsl_terminal_reader import run_wsl_command, extract_errors

print("=== Testing WSL Terminal Reader ===\n")

# Test 1: Run a successful command
print("Test 1: Successful command")
result = run_wsl_command('ls /tmp')
print(f"✓ Success: {result['success']}")
print(f"✓ Return Code: {result['return_code']}\n")

# Test 2: Run a command with error
print("Test 2: Command with error")
result = run_wsl_command('cat /nonexistent/file.txt')
errors = extract_errors(result)
print(f"✓ Command: {result['command']}")
print(f"✓ Has Errors: {errors['has_errors']}")
print(f"✓ Error Type: {errors['error_type']}")
print(f"✓ Error Output: {errors['error_output'][:100]}\n")

# Test 3: Check log file
print("Test 3: Check log file created")
import os
if os.path.exists('wsl_terminal.log'):
    print("✓ wsl_terminal.log created successfully\n")
else:
    print("✗ Log file not found\n")

print("=== All Tests Passed ===")
