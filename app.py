from flask import Flask, request, jsonify, render_template
import json
import os

app = Flask(__name__)

# ===== In-memory Project State =====
project = {"name": "未命名项目", "configs": [], "shared_items": []}
project_path = None


def find_config(name):
    for c in project.get("configs", []):
        if c["name"] == name:
            return c
    return None


def find_section(config_name, section_name):
    cfg = find_config(config_name)
    if cfg:
        for s in cfg.get("sections", []):
            if s["name"] == section_name:
                return s
    return None


def find_item(config_name, key, section_name=None):
    if section_name:
        sec = find_section(config_name, section_name)
        if sec:
            for item in sec.get("items", []):
                if item["key"] == key:
                    return item, sec["items"]
        return None, None
    cfg = find_config(config_name)
    if cfg:
        for item in cfg.get("items", []):
            if item["key"] == key:
                return item, cfg["items"]
    return None, None


def deep_copy(obj):
    return json.loads(json.dumps(obj))


def export_config(config):
    path = config.get("save_path", "")
    if not path:
        raise ValueError(f"配置 '{config['name']}' 未设置保存路径")

    cfg_copy = deep_copy(config)
    config_name = cfg_copy["name"]
    for si in project.get("shared_items", []):
        if config_name in si.get("target_configs", []):
            section_name = si.get("section", "")
            if section_name:
                sec = None
                for s in cfg_copy.get("sections", []):
                    if s["name"] == section_name:
                        sec = s
                        break
                if not sec:
                    sec = {"name": section_name, "description": "", "items": []}
                    cfg_copy.setdefault("sections", []).append(sec)
                if not any(i["key"] == si["key"] for i in sec["items"]):
                    sec["items"].append({
                        "key": si["key"],
                        "value": si["value"],
                        "description": si.get("description", "")
                    })
            else:
                if not any(i["key"] == si["key"] for i in cfg_copy.get("items", [])):
                    cfg_copy.setdefault("items", []).append({
                        "key": si["key"],
                        "value": si["value"],
                        "description": si.get("description", "")
                    })

    lines = []
    for item in cfg_copy.get("items", []):
        if item.get("description"):
            lines.append(f"; {item['description']}")
        lines.append(f"{item['key']} = {item['value']}")
        lines.append("")
    for section in cfg_copy.get("sections", []):
        lines.append(f"[{section['name']}]")
        if section.get("description"):
            lines.append(f"; {section['description']}")
        for item in section.get("items", []):
            if item.get("description"):
                lines.append(f"; {item['description']}")
            lines.append(f"{item['key']} = {item['value']}")
        lines.append("")

    abs_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines).strip() + '\n')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/project', methods=['GET', 'POST'])
def handle_project():
    global project, project_path

    if request.method == 'GET':
        resp = dict(project)
        resp['_save_path'] = project_path or ''
        return jsonify(resp)

    data = request.get_json(force=True)
    action = data.get('action')

    if action == 'new':
        project = {
            "name": data.get('name', '新项目'),
            "configs": [],
            "shared_items": []
        }
        project_path = None
        return jsonify(project)

    elif action == 'save':
        path = data.get('path')
        if path:
            project_path = path
        if not project_path:
            return jsonify({'error': '未指定保存路径'}), 400
        abs_path = os.path.abspath(project_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, 'w', encoding='utf-8') as f:
            json.dump(project, f, ensure_ascii=False, indent=2)
        return jsonify({'success': True, 'path': project_path})

    elif action == 'open':
        path = data.get('path')
        if not path or not os.path.exists(path):
            return jsonify({'error': '文件不存在'}), 404
        with open(path, 'r', encoding='utf-8') as f:
            project = json.load(f)
        project_path = path
        return jsonify(project)

    elif action == 'export':
        errors = []
        for config in project.get('configs', []):
            try:
                export_config(config)
            except Exception as e:
                errors.append(f"{config['name']}: {str(e)}")
        if errors:
            return jsonify({'success': False, 'errors': errors})
        return jsonify({'success': True, 'errors': []})

    return jsonify({'error': '未知操作'}), 400


@app.route('/api/configs', methods=['POST'])
def add_config():
    data = request.get_json(force=True)
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': '配置名称不能为空'}), 400
    if find_config(name):
        return jsonify({'error': f'配置 "{name}" 已存在'}), 400
    cfg = {
        "name": name,
        "description": data.get('description', ''),
        "save_path": data.get('save_path', ''),
        "sections": [],
        "items": []
    }
    project["configs"].append(cfg)
    return jsonify(cfg), 201


@app.route('/api/configs/<name>', methods=['PUT'])
def update_config(name):
    cfg = find_config(name)
    if not cfg:
        return jsonify({'error': '配置未找到'}), 404
    data = request.get_json(force=True)
    new_name = data.get('name', '').strip()
    if new_name and new_name != name:
        if find_config(new_name):
            return jsonify({'error': f'配置 "{new_name}" 已存在'}), 400
        cfg['name'] = new_name
    if 'description' in data:
        cfg['description'] = data['description']
    if 'save_path' in data:
        cfg['save_path'] = data['save_path']
    return jsonify(cfg)


@app.route('/api/configs/<name>', methods=['DELETE'])
def delete_config(name):
    project["configs"] = [c for c in project["configs"] if c["name"] != name]
    for si in project.get("shared_items", []):
        si["target_configs"] = [t for t in si.get("target_configs", []) if t != name]
    return jsonify({'success': True})


@app.route('/api/configs/<config_name>/sections', methods=['POST'])
def add_section(config_name):
    cfg = find_config(config_name)
    if not cfg:
        return jsonify({'error': '配置未找到'}), 404
    data = request.get_json(force=True)
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': '节名称不能为空'}), 400
    if any(s['name'] == name for s in cfg.get('sections', [])):
        return jsonify({'error': f'节 "{name}" 已存在'}), 400
    sec = {"name": name, "description": data.get('description', ''), "items": []}
    cfg.setdefault('sections', []).append(sec)
    return jsonify(sec), 201


@app.route('/api/configs/<config_name>/sections/<section_name>', methods=['PUT'])
def update_section(config_name, section_name):
    sec = find_section(config_name, section_name)
    if not sec:
        return jsonify({'error': '节未找到'}), 404
    data = request.get_json(force=True)
    new_name = data.get('name', '').strip()
    if new_name and new_name != section_name:
        cfg = find_config(config_name)
        if any(s['name'] == new_name for s in cfg.get('sections', [])):
            return jsonify({'error': f'节 "{new_name}" 已存在'}), 400
        sec['name'] = new_name
    if 'description' in data:
        sec['description'] = data['description']
    return jsonify(sec)


@app.route('/api/configs/<config_name>/sections/<section_name>', methods=['DELETE'])
def delete_section(config_name, section_name):
    cfg = find_config(config_name)
    if not cfg:
        return jsonify({'error': '配置未找到'}), 404
    cfg['sections'] = [s for s in cfg['sections'] if s['name'] != section_name]
    return jsonify({'success': True})


@app.route('/api/configs/<config_name>/items', methods=['POST'])
def add_item(config_name):
    cfg = find_config(config_name)
    if not cfg:
        return jsonify({'error': '配置未找到'}), 404
    data = request.get_json(force=True)
    key = data.get('key', '').strip()
    if not key:
        return jsonify({'error': '配置项键不能为空'}), 400
    section_name = data.get('section', '').strip()

    if section_name:
        sec = find_section(config_name, section_name)
        if not sec:
            return jsonify({'error': f'节 "{section_name}" 未找到'}), 404
        if any(i['key'] == key for i in sec.get('items', [])):
            return jsonify({'error': f'配置项 "{key}" 已存在'}), 400
        item = {"key": key, "value": data.get('value', ''), "description": data.get('description', '')}
        sec.setdefault('items', []).append(item)
    else:
        if any(i['key'] == key for i in cfg.get('items', [])):
            return jsonify({'error': f'配置项 "{key}" 已存在'}), 400
        item = {"key": key, "value": data.get('value', ''), "description": data.get('description', '')}
        cfg.setdefault('items', []).append(item)
    return jsonify(item), 201


@app.route('/api/configs/<config_name>/items/<key>', methods=['PUT'])
def update_item(config_name, key):
    section_name = request.args.get('section', '').strip() or None
    item, items_list = find_item(config_name, key, section_name)
    if not item:
        return jsonify({'error': '配置项未找到'}), 404
    data = request.get_json(force=True)
    new_key = data.get('key', '').strip()
    if new_key and new_key != key:
        if any(i['key'] == new_key for i in items_list):
            return jsonify({'error': f'配置项 "{new_key}" 已存在'}), 400
        item['key'] = new_key
    if 'value' in data:
        item['value'] = data['value']
    if 'description' in data:
        item['description'] = data['description']
    return jsonify(item)


@app.route('/api/configs/<config_name>/items/<key>', methods=['DELETE'])
def delete_item(config_name, key):
    section_name = request.args.get('section', '').strip() or None
    cfg = find_config(config_name)
    if not cfg:
        return jsonify({'error': '配置未找到'}), 404
    if section_name:
        sec = find_section(config_name, section_name)
        if not sec:
            return jsonify({'error': '节未找到'}), 404
        sec['items'] = [i for i in sec.get('items', []) if i['key'] != key]
    else:
        cfg['items'] = [i for i in cfg.get('items', []) if i['key'] != key]
    return jsonify({'success': True})


@app.route('/api/shared', methods=['POST'])
def add_shared_item():
    data = request.get_json(force=True)
    key = data.get('key', '').strip()
    if not key:
        return jsonify({'error': '共享配置项键不能为空'}), 400
    if any(si['key'] == key for si in project.get('shared_items', [])):
        return jsonify({'error': f'共享配置项 "{key}" 已存在'}), 400
    si = {
        "key": key,
        "value": data.get('value', ''),
        "description": data.get('description', ''),
        "section": data.get('section', ''),
        "target_configs": data.get('target_configs', [])
    }
    project.setdefault('shared_items', []).append(si)
    return jsonify(si), 201


@app.route('/api/shared/<key>', methods=['PUT'])
def update_shared_item(key):
    for si in project.get('shared_items', []):
        if si['key'] == key:
            data = request.get_json(force=True)
            new_key = data.get('key', '').strip()
            if new_key and new_key != key:
                if any(s['key'] == new_key for s in project['shared_items']):
                    return jsonify({'error': f'共享配置项 "{new_key}" 已存在'}), 400
                si['key'] = new_key
            if 'value' in data:
                si['value'] = data['value']
            if 'description' in data:
                si['description'] = data['description']
            if 'section' in data:
                si['section'] = data['section']
            if 'target_configs' in data:
                si['target_configs'] = data['target_configs']
            return jsonify(si)
    return jsonify({'error': '共享配置项未找到'}), 404


@app.route('/api/shared/<key>', methods=['DELETE'])
def delete_shared_item(key):
    project['shared_items'] = [si for si in project.get('shared_items', []) if si['key'] != key]
    return jsonify({'success': True})


@app.route('/api/browse-save', methods=['POST'])
def browse_save():
    data = request.get_json(force=True)
    ext = data.get('ext', '.ini')
    filename = data.get('filename', '')
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.asksaveasfilename(
            defaultextension=ext,
            initialfile=filename,
            filetypes=[(f'*{ext}', f'*{ext}'), ('All files', '*.*')]
        )
        root.destroy()
        return jsonify({'path': path or ''})
    except Exception as e:
        return jsonify({'error': str(e), 'path': ''}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
