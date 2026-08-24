from pathlib import Path

def print_tree(path, max_depth=1, prefix="", depth=0):
    path = Path(path)
    items = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))

    for i, item in enumerate(items):
        connector = "└── " if i == len(items) - 1 else "├── "
        print(prefix + connector + item.name)

        if item.is_dir() and depth < max_depth:
            extension = "    " if i == len(items) - 1 else "│   "
            print_tree(item, max_depth, prefix + extension, depth + 1)

# Change "." to your project path if needed
print(Path(".").resolve().name)
print_tree(".", max_depth=1)