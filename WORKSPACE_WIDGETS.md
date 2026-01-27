# Workspace Custom Blocks in Frappe v14

## Overview

Custom dashboard widgets in Frappe v14 are stored in the database via DocType `Custom HTML Block`.
There is NO `frappe.workspace_block.registry` - that does not exist in Frappe.
Custom blocks use `frappe.create_shadow_element()` to render HTML/CSS/Script from DB.

## Database Structure

### Tables

1. **`tabCustom HTML Block`** - Contains the actual widget definitions
   - `name`: Block identifier (e.g., "Banking Health")
   - `html`: HTML template
   - `script`: JavaScript code (uses `root_element` as container reference)
   - `style`: CSS styles

2. **`tabWorkspace Custom Block`** - Links blocks to workspaces (child table)
   - `custom_block_name`: References `tabCustom HTML Block.name`
   - `parent`: Workspace name
   - `parentfield`: "custom_blocks"
   - `parenttype`: "Workspace"

3. **`tabWorkspace`** - Workspace definition
   - `content`: JSON array defining layout with block references

## How to Query/Update Blocks

```bash
# Get database credentials
cat /home/frappe/frappe-bench/sites/<site>/site_config.json | grep -E 'db_name|db_password'

# List all custom blocks
mysql -u <db_user> -p<db_pass> <db_name> -e "SELECT name FROM \`tabCustom HTML Block\`"

# View block definition
mysql -u <db_user> -p<db_pass> <db_name> -e "SELECT name, html, script, style FROM \`tabCustom HTML Block\` WHERE name = 'Banking Health'\G"

# Update block script
mysql -u <db_user> -p<db_pass> <db_name> << 'EOF'
UPDATE `tabCustom HTML Block`
SET script = 'your javascript here'
WHERE name = 'Banking Health';
EOF

# Clear cache after DB changes
bench --site <site> clear-cache
```

## Script Environment

Inside `script` field:
- `root_element` - The DOM container for this block instance
- `frappe` - Full Frappe JS API available
- No module imports, pure vanilla JS
- Use `frappe.call()` for API requests

## Example Block Script Pattern

```javascript
function loadData() {
    const contentEl = root_element.querySelector('.content');
    const loadingEl = root_element.querySelector('.loading');

    loadingEl.style.display = 'block';

    frappe.call({
        method: 'myapp.api.get_data',
        callback: function(r) {
            loadingEl.style.display = 'none';
            if (r.message) {
                contentEl.innerHTML = buildHTML(r.message);
            }
        }
    });
}

// Initial load
loadData();

// Refresh button
root_element.querySelector('.refresh-btn').addEventListener('click', loadData);

// Auto-refresh
setInterval(loadData, 60000);
```

## Workspace JSON Content Structure

```json
[
  {"id": "xyz", "type": "header", "data": {"text": "<span class=\"h4\">Title</span>", "col": 12}},
  {"id": "abc", "type": "custom_block", "data": {"custom_block_name": "Banking Health", "col": 6}},
  {"id": "def", "type": "shortcut", "data": {"shortcut_name": "My Shortcut", "col": 3}}
]
```

## Current Hibiscus Connect Blocks

### Banking Health
- **API**: `hibiscus_connect.api.get_comprehensive_health`
- **Shows**: Frappe scheduler, Hibiscus server status, scheduler, uptime, pending jobs, sync stats
- **Location**: `tabCustom HTML Block` WHERE name = 'Banking Health'

### Banking Account Status
- **API**: `hibiscus_connect.api.get_account_status`
- **Shows**: Bank accounts with balances and daily changes
- **Location**: `tabCustom HTML Block` WHERE name = 'Banking Account Status'

## Debugging

1. Check if block exists: Query `tabCustom HTML Block`
2. Check workspace references: Query `tabWorkspace Custom Block`
3. Browser console: Look for JS errors in block script
4. API test: `bench --site <site> execute hibiscus_connect.api.get_comprehensive_health`

## Important Notes

- Always escape quotes properly when updating via SQL
- Clear cache after any DB changes to blocks
- Browser hard refresh (Ctrl+Shift+R) may be needed
- Block scripts run in isolated scope with `root_element` as anchor
