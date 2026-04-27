"""
Environment Verification Script for Whisper Transcription
Checks all prerequisites before running the main transcription script
"""

import sys
import subprocess
import platform

def print_section(title):
    """Print formatted section header"""
    print(f"\n{'='*80}")
    print(f" {title}")
    print(f"{'='*80}\n")

def print_result(check_name, status, details="", recommendation=""):
    """Print check result with status"""
    status_symbol = "✓" if status else "✗"
    status_text = "PASS" if status else "FAIL"
    
    print(f"{status_symbol} {check_name}: {status_text}")
    if details:
        print(f"  → {details}")
    if recommendation:
        print(f"  ⚠ {recommendation}")
    print()

def check_python_version():
    """Check if Python version is compatible"""
    print_section("Python Version Check")
    
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    
    # Whisper requires Python 3.8+
    is_compatible = version.major == 3 and version.minor >= 8
    
    print_result(
        "Python Version",
        is_compatible,
        f"Version {version_str} detected",
        "Please install Python 3.8 or higher" if not is_compatible else ""
    )
    
    return is_compatible

def check_pip():
    """Check if pip is available"""
    print_section("Package Manager Check")
    
    try:
        result = subprocess.run(
            ["pip", "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        pip_version = result.stdout.strip()
        print_result("pip", True, pip_version)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_result(
            "pip",
            False,
            recommendation="pip not found. Reinstall Python with pip included"
        )
        return False

def check_ffmpeg():
    """Check if ffmpeg is installed"""
    print_section("FFmpeg Check")
    
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            check=True
        )
        # Get first line which contains version info
        ffmpeg_version = result.stdout.split('\n')[0]
        print_result("FFmpeg", True, ffmpeg_version)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_result(
            "FFmpeg",
            False,
            recommendation="Install FFmpeg using: choco install ffmpeg -y"
        )
        return False

def check_gpu_cuda():
    """Check CUDA and GPU availability"""
    print_section("GPU & CUDA Check")
    
    # Check NVIDIA GPU using nvidia-smi
    gpu_available = False
    gpu_name = "Not detected"
    cuda_version = "Not detected"
    
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=True
        )
        
        if result.stdout:
            gpu_info = result.stdout.strip().split(',')
            gpu_name = gpu_info[0].strip()
            driver_version = gpu_info[1].strip()
            memory = gpu_info[2].strip()
            
            gpu_available = True
            print_result(
                "NVIDIA GPU",
                True,
                f"{gpu_name} | Driver: {driver_version} | Memory: {memory}"
            )
        
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_result(
            "NVIDIA GPU",
            False,
            "nvidia-smi not found",
            "NVIDIA drivers may not be installed. Visit https://www.nvidia.com/drivers"
        )
    
    # Check CUDA version
    try:
        result = subprocess.run(
            ["nvcc", "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse CUDA version from output
        for line in result.stdout.split('\n'):
            if 'release' in line.lower():
                cuda_version = line.strip()
                break
        
        print_result("CUDA Toolkit", True, cuda_version)
        
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_result(
            "CUDA Toolkit",
            False,
            "nvcc not found",
            "CUDA Toolkit not installed (but might not be required if using PyTorch with bundled CUDA)"
        )
    
    return gpu_available

def check_python_packages():
    """Check if required Python packages are installed"""
    print_section("Python Packages Check")
    
    packages = {
        'torch': 'PyTorch',
        'whisper': 'OpenAI Whisper',
        'ffmpeg': 'ffmpeg-python'
    }
    
    all_installed = True
    
    for package, display_name in packages.items():
        try:
            if package == 'whisper':
                # Whisper is imported as 'whisper' but installed as 'openai-whisper'
                __import__('whisper')
            else:
                __import__(package)
            
            # Get version if available
            try:
                if package == 'torch':
                    import torch
                    version = torch.__version__
                elif package == 'whisper':
                    import whisper
                    # Whisper doesn't have __version__, so we just confirm it's installed
                    version = "installed"
                else:
                    mod = __import__(package)
                    version = getattr(mod, '__version__', 'version unknown')
                
                print_result(display_name, True, f"Version: {version}")
            except:
                print_result(display_name, True, "installed")
                
        except ImportError:
            print_result(
                display_name,
                False,
                recommendation=f"Install with: pip install {package if package != 'whisper' else 'openai-whisper'}"
            )
            all_installed = False
    
    return all_installed

def check_pytorch_cuda():
    """Check if PyTorch can access CUDA"""
    print_section("PyTorch CUDA Integration Check")
    
    try:
        import torch
        
        cuda_available = torch.cuda.is_available()
        
        if cuda_available:
            device_count = torch.cuda.device_count()
            device_name = torch.cuda.get_device_name(0)
            cuda_version = torch.version.cuda
            
            print_result(
                "PyTorch CUDA Support",
                True,
                f"Detected {device_count} GPU(s): {device_name} | CUDA {cuda_version}"
            )
            
            # Check memory
            try:
                props = torch.cuda.get_device_properties(0)
                total_memory_gb = props.total_memory / 1e9
                print_result(
                    "GPU Memory",
                    True,
                    f"{total_memory_gb:.2f} GB available"
                )
                
                # Recommendation based on memory
                if total_memory_gb < 8:
                    print(f"  ⚠ Warning: Low GPU memory. Consider using 'medium' or 'small' Whisper model")
                elif total_memory_gb >= 16:
                    print(f"  ✓ Excellent: Enough memory for 'large-v3' model (recommended)")
                
            except Exception as e:
                print(f"  Could not check GPU memory: {e}")
            
            return True
        else:
            print_result(
                "PyTorch CUDA Support",
                False,
                "CUDA not available to PyTorch",
                "Reinstall PyTorch with CUDA support: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121"
            )
            return False
            
    except ImportError:
        print_result(
            "PyTorch CUDA Support",
            False,
            "PyTorch not installed",
            "Install PyTorch first"
        )
        return False

def check_disk_space():
    """Check available disk space"""
    print_section("Disk Space Check")
    
    try:
        import shutil
        
        # Check system drive (usually C: on Windows)
        total, used, free = shutil.disk_usage("C:\\")
        
        free_gb = free / (1024**3)
        total_gb = total / (1024**3)
        
        # Whisper models can be 1-3GB, plus output files
        sufficient = free_gb > 10
        
        print_result(
            "Available Disk Space",
            sufficient,
            f"{free_gb:.2f} GB free of {total_gb:.2f} GB total on C:",
            "Low disk space. Free up at least 10GB for models and output files" if not sufficient else ""
        )
        
        return sufficient
        
    except Exception as e:
        print(f"Could not check disk space: {e}")
        return True

def test_gpu_computation():
    """Run a simple GPU computation test"""
    print_section("GPU Computation Test")
    
    try:
        import torch
        
        if not torch.cuda.is_available():
            print_result(
                "GPU Test",
                False,
                "CUDA not available - skipping GPU test"
            )
            return False
        
        # Simple tensor operation on GPU
        device = torch.device("cuda")
        x = torch.randn(1000, 1000, device=device)
        y = torch.randn(1000, 1000, device=device)
        z = torch.matmul(x, y)
        
        print_result(
            "GPU Computation Test",
            True,
            "Successfully performed matrix multiplication on GPU"
        )
        
        return True
        
    except Exception as e:
        print_result(
            "GPU Computation Test",
            False,
            f"Error: {str(e)}",
            "GPU computation failed - check CUDA installation"
        )
        return False

def print_system_info():
    """Print system information"""
    print_section("System Information")
    
    print(f"Operating System: {platform.system()} {platform.release()}")
    print(f"Platform: {platform.platform()}")
    print(f"Processor: {platform.processor()}")
    print(f"Python Executable: {sys.executable}")
    print()

def main():
    """Run all checks"""
    print("\n")
    print("╔" + "="*78 + "╗")
    print("║" + " "*20 + "WHISPER TRANSCRIPTION ENVIRONMENT CHECK" + " "*19 + "║")
    print("╚" + "="*78 + "╝")
    
    print_system_info()
    
    # Run all checks
    checks = {
        "Python Version": check_python_version(),
        "pip": check_pip(),
        "FFmpeg": check_ffmpeg(),
        "GPU Detection": check_gpu_cuda(),
        "Python Packages": check_python_packages(),
        "PyTorch CUDA": check_pytorch_cuda(),
        "Disk Space": check_disk_space(),
        "GPU Computation": test_gpu_computation()
    }
    
    # Summary
    print_section("Summary")
    
    passed = sum(checks.values())
    total = len(checks)
    
    print(f"Checks Passed: {passed}/{total}\n")
    
    if all(checks.values()):
        print("✓ " + "="*76 + " ✓")
        print("✓ ALL CHECKS PASSED! Your environment is ready for transcription." + " "*13 + "✓")
        print("✓ " + "="*76 + " ✓")
        print("\nYou can now run: python transcribe_german.py")
    else:
        print("✗ " + "="*76 + " ✗")
        print("✗ SOME CHECKS FAILED. Please address the issues above." + " "*19 + "✗")
        print("✗ " + "="*76 + " ✗")
        
        print("\nFailed checks:")
        for check_name, passed in checks.items():
            if not passed:
                print(f"  ✗ {check_name}")
        
        print("\nMost critical for GPU acceleration:")
        print("  1. Install FFmpeg: choco install ffmpeg -y")
        print("  2. Install packages: pip install openai-whisper torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
        print("  3. Update NVIDIA drivers if GPU not detected")
    
    print("\n")

if __name__ == "__main__":
    main()