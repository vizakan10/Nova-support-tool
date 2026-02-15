#!/usr/bin/env python3
"""
WSL Terminal Reader - Simple command execution and output capture for error tracking
"""

import subprocess
from datetime import datetime


def run_wsl_command(command, timeout=30, log_output=True):
    """
    Run a WSL command and capture its output
    
    Args:
        command: Command to execute in WSL
        timeout: Command timeout in seconds (default: 30)
        log_output: Whether to save output to log file (default: True)
        
    Returns:
        dict with stdout, stderr, return_code, success, and timestamp
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        # Run command directly in bash (we're already in WSL)
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            executable='/bin/bash'
        )
        
        output_dict = {
            'command': command,
            'timestamp': timestamp,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'return_code': result.returncode,
            'success': result.returncode == 0
        }
        
        # Log to file if requested
        if log_output:
            save_to_log(output_dict)
        
        return output_dict
        
    except subprocess.TimeoutExpired:
        output_dict = {
            'command': command,
            'timestamp': timestamp,
            'stdout': '',
            'stderr': f'Command timed out after {timeout} seconds',
            'return_code': -1,
            'success': False
        }
        if log_output:
            save_to_log(output_dict)
        return output_dict
        
    except Exception as e:
        output_dict = {
            'command': command,
            'timestamp': timestamp,
            'stdout': '',
            'stderr': f'Error: {str(e)}',
            'return_code': -1,
            'success': False
        }
        if log_output:
            save_to_log(output_dict)
        return output_dict


def save_to_log(output_dict, log_file="wsl_terminal.log"):
    """
    Save command output to log file
    
    Args:
        output_dict: Dictionary containing command results
        log_file: Path to log file
    """
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*70}\n")
            f.write(f"[{output_dict['timestamp']}]\n")
            f.write(f"Command: {output_dict['command']}\n")
            f.write(f"Return Code: {output_dict['return_code']}\n")
            f.write(f"Success: {output_dict['success']}\n")
            
            if output_dict['stdout']:
                f.write(f"\n--- STDOUT ---\n{output_dict['stdout']}\n")
            
            if output_dict['stderr']:
                f.write(f"\n--- STDERR (ERRORS) ---\n{output_dict['stderr']}\n")
                
    except Exception as e:
        print(f"Error writing to log: {e}")


def extract_errors(output_dict):
    """
    Extract error information from command output
    
    Args:
        output_dict: Dictionary from run_wsl_command
        
    Returns:
        dict with error analysis
    """
    has_errors = bool(output_dict['stderr']) or not output_dict['success']
    
    error_info = {
        'has_errors': has_errors,
        'return_code': output_dict['return_code'],
        'error_output': output_dict['stderr'],
        'command': output_dict['command'],
        'timestamp': output_dict['timestamp']
    }
    
    # Try to identify common error types
    if output_dict['stderr']:
        stderr_lower = output_dict['stderr'].lower()
        
        if 'permission denied' in stderr_lower:
            error_info['error_type'] = 'Permission Error'
        elif 'no such file' in stderr_lower or 'not found' in stderr_lower:
            error_info['error_type'] = 'File Not Found'
        elif 'syntax error' in stderr_lower:
            error_info['error_type'] = 'Syntax Error'
        elif 'connection' in stderr_lower:
            error_info['error_type'] = 'Connection Error'
        else:
            error_info['error_type'] = 'Unknown Error'
    else:
        error_info['error_type'] = 'None'
    
    return error_info


def read_log(log_file="wsl_terminal.log", last_n_entries=10):
    """
    Read the last N entries from the log file
    
    Args:
        log_file: Path to log file
        last_n_entries: Number of recent entries to read
        
    Returns:
        String with log contents
    """
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Split by separator and get last N entries
        entries = content.split('='*70)
        recent_entries = entries[-last_n_entries:]
        
        return ('='*70).join(recent_entries)
        
    except FileNotFoundError:
        return "Log file not found. Run some commands first."
    except Exception as e:
        return f"Error reading log: {e}"


def viza_up():
    """
    'viza up' command - Reads the last command executed in WSL terminal 
    with its input and output for error analysis
    
    Returns:
        dict with last command, output, and error information
    """
    # Read the last command from bash history
    history_result = run_wsl_command("history | tail -1", log_output=False)
    
    if not history_result['success']:
        return {
            'error': 'Could not read terminal history',
            'details': history_result['stderr']
        }
    
    # Parse the history output (format: "  123  command")
    last_command = history_result['stdout'].strip()
    if last_command:
        # Remove the history number
        parts = last_command.split(None, 1)
        if len(parts) > 1:
            last_command = parts[1]
    
    # Now execute that command again to capture its output
    if last_command and last_command != "history | tail -1":
        result = run_wsl_command(last_command, log_output=False)
        error_info = extract_errors(result)
        
        context = {
            'command': last_command,
            'timestamp': result['timestamp'],
            'output': result['stdout'],
            'error': result['stderr'],
            'return_code': result['return_code'],
            'success': result['success'],
            'error_analysis': error_info
        }
        
        # Save to a separate file for LLM context
        save_viza_context(context)
        
        return context
    
    return {
        'error': 'No command found in history',
        'details': 'Run a command first, then use viza_up()'
    }


def save_viza_context(context, file="viza_context.txt"):
    """
    Save the captured context in a clean format for LLM processing
    
    Args:
        context: Dictionary with command execution details
        file: Output file name
    """
    try:
        with open(file, 'w', encoding='utf-8') as f:
            f.write("=== TERMINAL CONTEXT FOR ERROR ANALYSIS ===\n\n")
            f.write(f"Timestamp: {context['timestamp']}\n")
            f.write(f"Command Executed: {context['command']}\n")
            f.write(f"Success: {context['success']}\n")
            f.write(f"Return Code: {context['return_code']}\n\n")
            
            if context['output']:
                f.write("--- OUTPUT ---\n")
                f.write(context['output'])
                f.write("\n\n")
            
            if context['error']:
                f.write("--- ERROR OUTPUT ---\n")
                f.write(context['error'])
                f.write("\n\n")
            
            if context['error_analysis']['has_errors']:
                f.write("--- ERROR ANALYSIS ---\n")
                f.write(f"Error Type: {context['error_analysis']['error_type']}\n")
                f.write(f"Has Errors: {context['error_analysis']['has_errors']}\n")
        
        print(f"✓ Context saved to {file} - Ready for LLM analysis")
        
    except Exception as e:
        print(f"Error saving context: {e}")


def main():
    """Main entry point for the viza command"""
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "up":
            # viza up - capture last command
            print("📋 Capturing last terminal activity...\n")
            context = viza_up()
            
            if 'error' in context:
                print(f"❌ {context['error']}")
                if 'details' in context:
                    print(f"   {context['details']}")
            elif 'command' in context:
                print(f"✓ Command: {context['command']}")
                print(f"✓ Success: {'Yes' if context['success'] else 'No'}")
                print(f"✓ Return Code: {context['return_code']}")
                
                if context['error_analysis']['has_errors']:
                    print(f"✓ Error Type: {context['error_analysis']['error_type']}")
                    print(f"\n--- Error Output ---")
                    print(context['error'])
                else:
                    print(f"\n--- Output ---")
                    print(context['output'][:500])  # First 500 chars
                
                print(f"\n✓ Full context saved to viza_context.txt")
                print("  Ready for error analysis!")
        
        elif command == "log":
            # viza log - show recent log
            entries = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            print(f"📋 Last {entries} log entries:\n")
            print(read_log(last_n_entries=entries))
        
        elif command == "help" or command == "-h" or command == "--help":
            print("=== Viza - WSL Terminal Error Capture Tool ===\n")
            print("Usage:")
            print("  viza up          - Capture last command output and errors")
            print("  viza log [n]     - Show last n log entries (default: 5)")
            print("  viza help        - Show this help message")
            print("\nExample workflow:")
            print("  1. Run any command in terminal (e.g., python3 script.py)")
            print("  2. If it fails, run: viza up")
            print("  3. Check viza_context.txt for error details")
        
        else:
            print(f"Unknown command: {command}")
            print("Run 'viza help' for usage information")
    
    else:
        # No arguments - run examples
        print("=== WSL Terminal Reader - Examples ===\n")
        
        print("Example 1: Run a command")
        result = run_wsl_command("ls -la /home")
        print(f"Success: {result['success']}\n")
        
        print("Example 2: Capture an error")
        result = run_wsl_command("cat /nonexistent/file.txt")
        error_info = extract_errors(result)
        print(f"Error Type: {error_info['error_type']}")
        print(f"Error: {error_info['error_output']}\n")
        
        print("Example 3: Use 'viza up' command")
        context = viza_up()
        if 'command' in context:
            print(f"Captured: {context['command']}")
            print(f"Context saved to viza_context.txt\n")
        
        print("="*70)
        print("To use from command line:")
        print("  Run: bash install_viza.sh")
        print("  Then: viza up")
        print("  Or:   viza help")


if __name__ == "__main__":
    main()
    
    print("\n" + "="*70 + "\n")
    
    # Example 5: Using as an importable module
    print("Example 5: Using as an importable module")
    from wsl_terminal_reader import run_wsl_command, extract_errors
    
    # Run any WSL command
    result = run_wsl_command("your_command_here")
    
    # Check for errors
    error_info = extract_errors(result)
    if error_info['has_errors']:
        print(f"Error Type: {error_info['error_type']}")
        print(f"Error: {error_info['error_output']}")
