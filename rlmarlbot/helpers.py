import json
import ctypes


def struct_to_dict(struct):
    result = {}
    for field, _ in struct._fields_:
        value = getattr(struct, field)
        # Convertir des objets ctypes ou des structures personnalisées en dictionnaires
        if hasattr(value, "_length_") and hasattr(value, "_type_"):
            # C'est un tableau de ctypes
            result[field] = [struct_to_dict(item) if hasattr(item, "_fields_") else item for item in value]
        elif hasattr(value, "_fields_"):
            # C'est une structure ctypes
            result[field] = struct_to_dict(value)
        else:
            # Pour les types de base ctypes
            result[field] = value.value if isinstance(value, ctypes._SimpleCData) else value
    return result

def serialize_to_json(packet):
    packet_dict = struct_to_dict(packet)
    return json.dumps(packet_dict, indent=4)


def move_cursor_up(lines):
   
    print(f"\033[{lines}A", end="")

def clear_line():

    print("\033[K", end="")
    
    
def clear_lines(lines):

    for _ in range(lines):
        clear_line()
        move_cursor_up(1)
   
    
    
def clear_screen():
     print("\033[2J\033[H", end="")