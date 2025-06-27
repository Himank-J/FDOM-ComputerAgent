# Computer Agent 🤖

An innovative AI system designed to understand and interact with desktop applications using cutting-edge computer vision and large language models. It can "see" an application's interface, interpret natural language commands, and execute tasks by controlling the GUI.

The functional DOM (fDOM) pipeline is a modular system that automatically discovers UI elements of an application, captures their properties (including dynamic behaviors like hover text or menus), and assembles a structured JSON representation.

Functional DOM (fDOM) is an emergent paradigm for automated, machine-readable mapping of GUI applications. Using advanced perception and automation, our pipeline generates an fDOM JSON artifact that enumerates all visible UI elements, their properties, and initial relations—enabling both analysis and automation. 

## Exploration Phase
[Watch how Computer Agent works in Exploration Phase](https://drive.google.com/file/d/1rcYJeS_GEPTs0XPT526U-W6WV2CPVH6A/view?usp=sharing)

## FDOM For Notes Application

[fdom.json](!apps/notes/fdom.json)
```json
{
  "app_name": "notes",
  "loaded": false,
  "creation_timestamp": "2025-06-25T21:55:19.038281",
  "navigation_tree": {},
  "states": {
    "root": {
      "id": "root",
      "parent": null,
      "trigger_node": null,
      "trigger_element": "initial_state",
      "breadcrumb": "root",
      "image": "/Users/himank.jain/Downloads/S14B/apps/notes/screenshots/S001.png",
      "creation_timestamp": "2025-06-25T21:55:44.499204",
      "analysis_time": 0,
      "total_elements": 116,
      "nodes": {
        "H0_1": {
          "bbox": [
            25,
            0,
            83,
            64
          ],
          "g_icon_name": "unanalyzed",
          "g_brief": "Not analyzed by Gemini",
          "g_enabled": true,
          "g_interactive": true,
          "g_type": "icon",
          "m_id": null,
          "y_id": null,
          "o_id": null,
          "type": "icon",
          "source": "unknown",
          "group": "H0",
          "status": "pending"
        }
  "exit_strategies": {
        "root": {
          "method": "click_coordinates",
          "coordinates": [
            1899,
            192
          ],
          "learned_from": "automatic_discovery",
          "success_rate": 1.0,
          "last_used": 1751038940.530956,
          "discovery_method": "safe_area_click"
        }
      }
    }
  },
  "edges": [
    {
      "from": "root",
      "to": "root_blue_circle",
      "action": "click:H4_1",
      "element_name": "Blue Circle",
      "navigation": "root → root_blue_circle",
      "timestamp": "2025-06-25T22:28:42.681621"
    },
    {
      "from": "root",
      "to": "root_light_blue_circle",
      "action": "click:H4_2",
      "element_name": "Light Blue Circle",
      "navigation": "root → root_light_blue_circle",
      "timestamp": "2025-06-25T22:29:10.296432"
    },
    {
      "from": "root",
      "to": "root_edit",
      "action": "click:H5_1",
      "element_name": "Edit",
      "navigation": "root → root_edit",
      "timestamp": "2025-06-25T22:30:45.130177"
    },
    {
      "from": "root",
      "to": "root_+_new_folder",
      "action": "click:H3_1",
      "element_name": "+ New Folder",
      "navigation": "root → root_+_new_folder",
      "timestamp": "2025-06-27T21:08:59.419111"
    },
    {
      "from": "root",
      "to": "root_+_new_folder",
      "action": "click:H3_1",
      "element_name": "+ New Folder",
      "navigation": "root → root_+_new_folder",
      "timestamp": "2025-06-27T21:12:11.496593"
    }
  ],
  "last_updated": "2025-06-27T21:12:20.531036",
  "total_states": 5,
  "exploration_stats": {
    "pending_nodes": 214,
    "explored_nodes": 0,
    "non_interactive_nodes": 0,
    "total_nodes": 214
  }
}
```

[metadata.json](!https://github.com/Himank-J/FDOM-ComputerAgent/blob/main/apps/notes/metadata.json)
```
{
  "app_name": "notes",
  "created_timestamp": "2025-06-27T21:11:49Z",
  "fdom_creator_version": "1.0.0",
  "exploration_status": "initialized",
  "folder_structure": {
    "screenshots": "screenshots",
    "crops": "crops",
    "diffs": "screenshots/diffs",
    "templates": "templates"
  }
}

```

## Screenshots

[**S001**](!apps/notes/screenshots/S001.png)

![S001](https://github.com/user-attachments/assets/86144769-ba97-4488-8dea-93e6047ce249)

[**Diff**](!apps/notes/screenshots/diffs/root_to_processing_via_root__H3_1.png)

<img width="1425" alt="image" src="https://github.com/user-attachments/assets/45963ecb-1e07-4a8c-adff-bd32cee2a624" />

## Logs

<img width="716" alt="image" src="https://github.com/user-attachments/assets/7d1986da-2226-48fe-a2bc-591787cf122e" />


