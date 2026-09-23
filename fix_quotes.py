import os

def fix_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content
    # Replace curly/smart quotes with plain ASCII quotes
    content = content.replace('\u201c', '"').replace('\u201d', '"')
    content = content.replace('\u2018', "'").replace('\u2019', "'")
    if content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'Fixed: {path}')

for root, dirs, files in os.walk('any2md'):
    for fname in files:
        if fname.endswith('.py'):
            fix_file(os.path.join(root, fname))
print('Done')
