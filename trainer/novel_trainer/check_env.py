import platform
import sys

print("Python:", sys.version.replace("\n", " "))
print("OS:", platform.platform())
try:
    import torch
    print("PyTorch:", torch.__version__)
    print("CUDA available:", torch.cuda.is_available())
    print("PyTorch CUDA:", torch.version.cuda)
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))
        props = torch.cuda.get_device_properties(0)
        print("VRAM GiB:", round(props.total_memory / 1024**3, 2))
except Exception as e:
    print("PyTorch error:", repr(e))

for name in ["transformers", "peft", "bitsandbytes", "accelerate", "PySide6"]:
    try:
        mod = __import__(name)
        print(f"{name}:", getattr(mod, "__version__", "OK"))
    except Exception as e:
        print(f"{name}: ERROR", repr(e))
