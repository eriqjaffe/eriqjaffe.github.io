bl_info = {
    "name": "OOTP Ballpark Toolkit",
    "author": "Eriq Jaffe",
    "version": (0, 6, 1),
    "blender": (4, 0, 0),
    "location": "3D Viewport > Main Top Bar (Next to Object Menu)",
    "description": "Custom workflow utilities for Out of the Park Baseball stadium creation.",
    "category": "3D View",
}

import bpy
import os
import re
import sys
import time
import math
import json
from bpy_extras.io_utils import ExportHelper

CONFIG_DIR = bpy.utils.user_resource('CONFIG', path="ootp-ballpark-toolkit", create=True)
CONFIG_FILE_PATH = os.path.join(CONFIG_DIR, "defaults.json")

FALLBACK_DEFAULTS = {
    "sky_texture_defaults": {
        "sky_type": "MULTIPLE_SCATTERING",
        "sun_intensity": 0.200,
        "sun_elevation": 27,
        "sun_rotation": -190,
        "strength": 0.200
    },
    "material_emission_defaults": {}
}

USER_SETTINGS = {} 

def load_user_defaults():
    """Loads settings from the JSON file, or creates it with fallbacks if missing."""
    if not os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(FALLBACK_DEFAULTS, f, indent=4)
            return FALLBACK_DEFAULTS
        except IOError:
            print(f"Add-on Warning: Could not write default file to {CONFIG_FILE_PATH}")
            return FALLBACK_DEFAULTS

    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Add-on Error: Failed to parse custom JSON. Using defaults. Error: {e}")
        return FALLBACK_DEFAULTS

def ensure_system_console_open():
    """Ensures the Windows system console is open without accidentally toggling it closed."""
    if sys.platform == 'win32':
        import ctypes
        console_handle = ctypes.windll.kernel32.GetConsoleWindow()
        is_visible = ctypes.windll.user32.IsWindowVisible(console_handle) if console_handle else False
        if not console_handle or not is_visible:
            try:
                bpy.ops.wm.console_toggle()
            except Exception as e:
                print(f"Failed to toggle console: {e}")

def set_default_sky_texture(world):
    # set default daytime lighting
    node_tree = world.node_tree
    nodes = node_tree.nodes
    links = node_tree.links

    nodes.clear()

    node_output = nodes.new(type='ShaderNodeOutputWorld')
    node_output.location = (400, 0)

    node_background = nodes.new(type='ShaderNodeBackground')
    node_background.location = (200, 0)

    node_sky = nodes.new(type='ShaderNodeTexSky')
    node_sky.location = (0, 0)
    
    sky_data = USER_SETTINGS.get("sky_texture_defaults", {})

    node_sky.sky_type = sky_data.get('sky_type') 
    node_sky.sun_intensity = sky_data.get('sun_intensity')
    node_sky.sun_elevation = math.radians(sky_data.get('sun_rotation'))
    node_sky.sun_rotation = math.radians(sky_data.get('sun_rotation'))

    node_background.inputs['Strength'].default_value = sky_data.get('strength')

    links.new(node_sky.outputs['Color'], node_background.inputs['Color'])
    links.new(node_background.outputs['Background'], node_output.inputs['Surface'])
    
# ====================================================================
# Global Scene Cleanup (Renamed Class & ID)
# ====================================================================
class OOTP_OT_scene_cleaner(bpy.types.Operator):
    """Purge DefaultMaterial geometry and isolate valid textures globally"""
    bl_idname = "ootp.scene_cleaner"
    bl_label = "Clean Scene & Isolate Materials"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context): 
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Save your .blend file first!")
            return {'CANCELLED'}
            
        ensure_system_console_open()
        
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        loose_obj_name = "_(Loose Entity)"

        if loose_obj_name in bpy.data.objects:
            loose_obj = bpy.data.objects[loose_obj_name]
            loose_obj.name = "_(Loose Entity)_nobake"
            
        mesh_count = 0
        
        for obj in context.scene.objects:                
            if "nobake" in obj.name.lower():
                continue
            
            if obj.type == 'MESH':
                mesh_count += 1
                
                display_name = obj.name
                if display_name.startswith("C-"):
                    display_name = display_name.replace("C-", "", 1)
                    
                print(f"Processing {display_name}...")
                
                mesh = obj.data
                default_slot_indices = [i for i, slot in enumerate(obj.material_slots) if slot.material and slot.material.name == "DefaultMaterial"]
                
                # Purge Geometry
                if default_slot_indices:
                    faces_to_delete = [f.index for f in mesh.polygons if f.material_index in default_slot_indices]
                    
                    if faces_to_delete:
                        context.view_layer.objects.active = obj
                        bpy.ops.object.mode_set(mode='EDIT')
                        bpy.ops.mesh.select_all(action='DESELECT')
                        bpy.ops.object.mode_set(mode='OBJECT')
                        for f_idx in faces_to_delete:
                            mesh.polygons[f_idx].select = True
                            
                        bpy.ops.object.mode_set(mode='EDIT')
                        bpy.ops.mesh.delete(type='FACE')
                        bpy.ops.object.mode_set(mode='OBJECT')
                    
                    for idx in sorted(default_slot_indices, reverse=True):
                        obj.active_material_index = idx
                        bpy.ops.object.material_slot_remove()
                        
                # UV Maps Setup
                if not mesh.uv_layers:
                    source_uv = mesh.uv_layers.new(name="UVMap")
                else:
                    source_uv = next((layer for layer in mesh.uv_layers if layer.active_render), mesh.uv_layers[0])
                
                source_uv.active_render = True
                
                if display_name not in mesh.uv_layers:
                    target_uv = mesh.uv_layers.new(name=display_name)
                else:
                    target_uv = mesh.uv_layers[display_name]
    
                mesh.uv_layers.active = target_uv

                # Material Splitting
                for slot in obj.material_slots:
                    if slot.material:
                        orig_name = slot.material.name
                        if "." in orig_name and orig_name.split(".")[-1].isdigit():
                            orig_name = ".".join(orig_name.split(".")[:-1])
                        
                        new_mat = slot.material.copy()
                        new_mat.name = f"{orig_name}_{display_name}"
                        slot.material = new_mat

                clean_img_name = f"{display_name.replace(' ', '_')}_day.png"

                # Bake target
                if clean_img_name not in bpy.data.images:
                    bake_image = bpy.data.images.new(
                        name=clean_img_name,
                        width=1024,
                        height=1024,
                        alpha=True
                    )
                    bake_image.generated_color = (0.0, 0.0, 0.0, 0.0)
                    
                    blend_dir = bpy.path.abspath("//")
                    if blend_dir:
                        save_path = os.path.join(blend_dir, clean_img_name)    
                        bake_image.filepath_raw = save_path
                        bake_image.file_format = 'PNG'
                        bake_image.save()                   
                        bake_image.filepath = bpy.path.relpath(save_path)
                        bake_image.pack()
                    else:
                        print("Warning: Save your .blend file first so the script knows where to store images!")

                else:
                    bake_image = bpy.data.images[clean_img_name]

                for slot in obj.material_slots:
                    mat = slot.material
                    if not mat or not mat.use_nodes:
                        continue
                        
                    nodes = mat.node_tree.nodes
                    links = mat.node_tree.links
                    
                    for node in nodes:
                        node.select = False
                        
                    source_tex_node = next((n for n in nodes if n.type == 'TEX_IMAGE' and n.label != "Bake Target"), None)
                    output_node = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
                    principled_node = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
                    
                    if output_node:
                        right_x = output_node.location.x + 200
                        right_y = output_node.location.y
                    else:
                        right_x = 600
                        right_y = 300

                    uv_src_node = nodes.new(type='ShaderNodeUVMap')
                    uv_src_node.uv_map = source_uv.name
                    
                    if source_tex_node:
                        links.new(uv_src_node.outputs['UV'], source_tex_node.inputs['Vector'])
                        uv_src_node.location = (source_tex_node.location.x - 300, source_tex_node.location.y)
                    else:
                        uv_src_node.location = (right_x - 600, right_y)
                        
                    if source_tex_node and principled_node:
                        links.new(source_tex_node.outputs['Alpha'], principled_node.inputs['Alpha'])
                        
                    uv_tgt_node = nodes.new(type='ShaderNodeUVMap')
                    uv_tgt_node.uv_map = target_uv.name
                    uv_tgt_node.location = (right_x, right_y)
                    
                    tgt_tex_node = nodes.new(type='ShaderNodeTexImage')
                    tgt_tex_node.image = bake_image
                    tgt_tex_node.label = "Bake Target"
                    tgt_tex_node.location = (right_x + 300, right_y)
                        
                    links.new(uv_tgt_node.outputs['UV'], tgt_tex_node.inputs['Vector'])
                    
                    tgt_tex_node.select = True
                    nodes.active = tgt_tex_node

        # sky texture
        world = bpy.context.scene.world
        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        
        nodes.clear()
        
        world_output = nodes.new(type='ShaderNodeOutputWorld')
        background = nodes.new(type='ShaderNodeBackground')
        sky_texture = nodes.new(type='ShaderNodeTexSky')
        
        sky_texture.location = (-300, 0)
        background.location = (0, 0)
        world_output.location = (200, 0)
        
        sky_data = USER_SETTINGS.get("sky_texture_defaults", {})
        
        sky_texture.sky_type = sky_data.get('sky_type') 
        
        sky_texture.sun_elevation = math.radians(sky_data.get('sun_elevation'))
        sky_texture.sun_rotation = math.radians(sky_data.get('sun_rotation'))
        sky_texture.sun_intensity = sky_data.get('sun_intensity')
        background.inputs['Strength'].default_value = sky_data.get('strength')
        
        links.new(sky_texture.outputs['Color'], background.inputs['Color'])
        links.new(background.outputs['Background'], world_output.inputs['Surface'])
        
        self.report({'INFO'}, f"Processed {mesh_count} components. All UV maps, bakes, and target nodes configured!")
        return {'FINISHED'}
        
# ====================================================================
# Selected Object Cleanup
# ====================================================================
class OOTP_selected_scene_cleaner(bpy.types.Operator):
    """Purge DefaultMaterial geometry and isolate valid textures for selected object(s)"""
    bl_idname = "ootp.object_cleaner"
    bl_label = "Clean Scene & Isolate Materials for Selected Object(s)"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_meshes:
            print("Warning: No mesh objects were selected.")
        else:
            mesh_count = 0
            for obj in selected_meshes:
                if "nobake" in obj.name.lower():
                    continue
                
                if obj.type == 'MESH':
                    mesh_count += 1
                    display_name = obj.name
                    if display_name.startswith("C-"):
                        display_name = display_name.replace("C-", "", 1)
                        
                    mesh = obj.data
                    default_slot_indices = [i for i, slot in enumerate(obj.material_slots) if slot.material and slot.material.name == "DefaultMaterial"]
                    
                    # Purge Geometry
                    if default_slot_indices:
                        faces_to_delete = [f.index for f in mesh.polygons if f.material_index in default_slot_indices]
                        
                        if faces_to_delete:
                            context.view_layer.objects.active = obj
                            bpy.ops.object.mode_set(mode='EDIT')
                            bpy.ops.mesh.select_all(action='DESELECT')
                            bpy.ops.object.mode_set(mode='OBJECT')
                            for f_idx in faces_to_delete:
                                mesh.polygons[f_idx].select = True
                                
                            bpy.ops.object.mode_set(mode='EDIT')
                            bpy.ops.mesh.delete(type='FACE')
                            bpy.ops.object.mode_set(mode='OBJECT')
                        
                        for idx in sorted(default_slot_indices, reverse=True):
                            obj.active_material_index = idx
                            bpy.ops.object.material_slot_remove()
                            
                    # UV Maps Setup
                    if not mesh.uv_layers:
                        source_uv = mesh.uv_layers.new(name="UVMap")
                    else:
                        source_uv = next((layer for layer in mesh.uv_layers if layer.active_render), mesh.uv_layers[0])
                    
                    source_uv.active_render = True
                    
                    if display_name not in mesh.uv_layers:
                        target_uv = mesh.uv_layers.new(name=display_name)
                    else:
                        target_uv = mesh.uv_layers[display_name]
        
                    mesh.uv_layers.active = target_uv

                    # Material Splitting
                    for slot in obj.material_slots:
                        if slot.material:
                            orig_name = slot.material.name
                            if "." in orig_name and orig_name.split(".")[-1].isdigit():
                                orig_name = ".".join(orig_name.split(".")[:-1])
                            
                            new_mat = slot.material.copy()
                            new_mat.name = f"{orig_name}_{display_name}"
                            slot.material = new_mat

                    # Create Blank Bake Target Image
                    clean_img_name = f"{display_name.replace(' ', '_')}_day.png"  # Added extension

                if clean_img_name not in bpy.data.images:
                    bake_image = bpy.data.images.new(
                        name=clean_img_name,
                        width=1024,
                        height=1024,
                        alpha=True
                    )
                    bake_image.generated_color = (0.0, 0.0, 0.0, 0.0)
                    
                    blend_dir = bpy.path.abspath("//")
                    if blend_dir:
                        save_path = os.path.join(blend_dir, clean_img_name)
                        
                        bake_image.filepath_raw = save_path
                        bake_image.file_format = 'PNG'
                        bake_image.save()
                        
                        bake_image.filepath = bpy.path.relpath(save_path)
                        
                        bake_image.pack()
                    else:
                        print("Warning: Save your .blend file first so the script knows where to store images!")

                else:
                    bake_image = bpy.data.images[clean_img_name]

                    for slot in obj.material_slots:
                        mat = slot.material
                        if not mat or not mat.use_nodes:
                            continue
                            
                        nodes = mat.node_tree.nodes
                        links = mat.node_tree.links
                        
                        for node in nodes:
                            node.select = False
                            
                        source_tex_node = next((n for n in nodes if n.type == 'TEX_IMAGE' and n.label != "Bake Target"), None)
                        output_node = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
                        principled_node = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
                        
                        if output_node:
                            right_x = output_node.location.x + 200
                            right_y = output_node.location.y
                        else:
                            right_x = 600
                            right_y = 300

                        uv_src_node = nodes.new(type='ShaderNodeUVMap')
                        uv_src_node.uv_map = source_uv.name
                        
                        if source_tex_node:
                            links.new(uv_src_node.outputs['UV'], source_tex_node.inputs['Vector'])
                            uv_src_node.location = (source_tex_node.location.x - 300, source_tex_node.location.y)
                        else:
                            uv_src_node.location = (right_x - 600, right_y)
                            
                        if source_tex_node and principled_node:
                            links.new(source_tex_node.outputs['Alpha'], principled_node.inputs['Alpha'])
                            
                        uv_tgt_node = nodes.new(type='ShaderNodeUVMap')
                        uv_tgt_node.uv_map = target_uv.name
                        uv_tgt_node.location = (right_x, right_y)
                        
                        tgt_tex_node = nodes.new(type='ShaderNodeTexImage')
                        tgt_tex_node.image = bake_image
                        tgt_tex_node.label = "Bake Target"
                        tgt_tex_node.location = (right_x + 300, right_y)
                            
                        links.new(uv_tgt_node.outputs['UV'], tgt_tex_node.inputs['Vector'])
                        
                        tgt_tex_node.select = True
                        nodes.active = tgt_tex_node

        self.report({'INFO'}, f"Processed {mesh_count} components. All UV maps, bakes, and target nodes configured!")
        return {'FINISHED'}

# ====================================================================
# UV Unwrap entire model
# ====================================================================
class OOTP_UV_unwrap_global(bpy.types.Operator):
    """Smart UV Unwrap every bakeable component in the model"""
    bl_idname = "ootp.global_unwrap"
    bl_label = "UV Unwrap Entire Model"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        target_objects = [obj for obj in context.scene.objects if "nobake" not in obj.name.lower() and obj.type == 'MESH']
        
        if not target_objects:
            print("No 'nobake' mesh components found in the scene.")
            return

        print(f"Starting Smart UV Unwrap on {len(target_objects)} components...")

        unwrapped_count = 0
        
        bpy.ops.object.select_all(action='DESELECT')

        for obj in target_objects:
            context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.smart_project(
                angle_limit=66.0, 
                island_margin=0.02, 
                area_weight=0.0, 
                correct_aspect=True, 
                scale_to_bounds=False
            )
            
            bpy.ops.uv.pack_islands(
                margin=0.02,
                rotate=True,
                rotate_method='AXIS_ALIGNED', 
                shape_method='CONCAVE'
            )
            
            bpy.ops.object.mode_set(mode='OBJECT')
            obj.select_set(False)
            
            unwrapped_count += 1
            print(f"  -> Smart Unwrapped: {obj.name}")

        self.report({'INFO'}, f"Finished! Successfully unwrap-prepped {unwrapped_count} components.")
        return {'FINISHED'}
        
# ====================================================================
# UV Unwrap selected objects
# ====================================================================
class OOTP_UV_unwrap_selected(bpy.types.Operator):
    """Smart UV Unwrap every bakeable component in the model"""
    bl_idname = "ootp.selected_unwrap"
    bl_label = "UV Unwrap Selected Objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        target_objects = [obj for obj in context.selected_objects if "nobake" not in obj.name.lower() and obj.type == 'MESH']
        
        if not target_objects:
            print("No 'nobake' mesh components found in the scene.")
            return

        unwrapped_count = 0
        
        print(f"Starting Smart UV Unwrap on {len(target_objects)} components...")

        bpy.ops.object.select_all(action='DESELECT')

        for obj in target_objects:
            context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.smart_project(
                angle_limit=66.0, 
                island_margin=0.02, 
                area_weight=0.0, 
                correct_aspect=True, 
                scale_to_bounds=False
            )
            
            bpy.ops.uv.pack_islands(
                margin=0.02,
                rotate=True,
                rotate_method='AXIS_ALIGNED', 
                shape_method='CONCAVE'
            )
            
            bpy.ops.object.mode_set(mode='OBJECT')
            obj.select_set(False)
            
            print(f"  -> Smart Unwrapped: {obj.name}")
            unwrapped_count += 1

        self.report({'INFO'}, f"Finished! Successfully unwrap-prepped {unwrapped_count} component(s).")
        return {'FINISHED'}

# ====================================================================
# Node Cloner (Renamed Class & ID to bypass cache)
# ====================================================================
class OOTP_OT_node_cloner(bpy.types.Operator):
    """Clone selected shader nodes to all other materials on the active component"""
    bl_idname = "ootp.node_cloner"
    bl_label = "Clone Nodes to Component Materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select your stadium component mesh first!")
            return {'CANCELLED'}
            
        active_mat = obj.active_material
        if not active_mat or not active_mat.use_nodes:
            self.report({'ERROR'}, "Active material must use nodes")
            return {'CANCELLED'}

        selected_nodes = [n for n in active_mat.node_tree.nodes if n.select]
        master_active = active_mat.node_tree.nodes.active

        if not selected_nodes:
            self.report({'WARNING'}, "No nodes selected in the Shader Editor!")
            return {'CANCELLED'}

        for mat_slot in obj.material_slots:
            mat = mat_slot.material
            if mat and mat != active_mat and mat.use_nodes:
                nodes = mat.node_tree.nodes
                for n in nodes:
                    n.select = False
                
                target_active_node = None
                for src_node in selected_nodes:
                    new_node = nodes.new(type=src_node.bl_idname)
                    if hasattr(src_node, "image"):
                        new_node.image = src_node.image
                    if hasattr(src_node, "uv_map"):
                        new_node.uv_map = src_node.uv_map
                        
                    new_node.location = src_node.location
                    new_node.select = True
                    if src_node == master_active:
                        target_active_node = new_node
                
                if target_active_node:
                    nodes.active = target_active_node

        self.report({'INFO'}, f"Nodes cloned across all materials for {obj.name}!")
        return {'FINISHED'}

# ====================================================================
# Replace all materials with baked materials where applicable
# ====================================================================
class OOTP_replace_all_materials(bpy.types.Operator):
    """Replace all materials with baked materials, where applicable"""
    bl_idname = "ootp.replace_all_materials"
    bl_label = "Replace all materials with baked textures"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        
        mesh_objects = [obj for obj in context.scene.objects if "nobake" not in obj.name.lower() and obj.type == 'MESH']
        mesh_objects = sorted(mesh_objects, key=lambda obj: obj.name.lower())
        
        replaced_count = 0
    
        for obj in mesh_objects:
            if "nobake" in obj.name.lower():
                continue
            
            if obj.type == 'MESH':
                obj_name = obj.name
                mat_name = obj_name[2:] if obj_name.startswith("C-") else obj_name
                
                obj.data.materials.clear()
        
                new_mat = bpy.data.materials.new(name=mat_name)
                new_mat.use_nodes = True
                nodes = new_mat.node_tree.nodes
                links = new_mat.node_tree.links
                
                nodes.clear()

                node_output  = nodes.new(type='ShaderNodeOutputMaterial')
                node_principled = nodes.new(type='ShaderNodeBsdfPrincipled')
                node_texture = nodes.new(type='ShaderNodeTexImage')
                node_uvmap   = nodes.new(type='ShaderNodeUVMap')
                
                node_uvmap.location = (-600, 0)
                node_texture.location = (-300, 0)
                node_principled.location = (0, 0)
                node_output.location = (300, 0)
                
                active_uv = obj.data.uv_layers.active
                if active_uv:
                    node_uvmap.uv_map = active_uv.name

                clean_img_name = f"{mat_name.replace(' ', '_')}_day.png"
                
                if bpy.data.is_saved:
                    absolute_blend_path = bpy.path.abspath(bpy.data.filepath)
                    blend_dir = os.path.dirname(absolute_blend_path)
                    full_image_path = os.path.join(blend_dir, clean_img_name)
                    
                    if os.path.exists(full_image_path):
                        try:
                            if clean_img_name in bpy.data.images:
                                baked_texture = bpy.data.images[clean_img_name]
                                
                                if baked_texture.packed_file:
                                    baked_texture.unpack(method='USE_LOCAL')
                                baked_texture.filepath = full_image_path
                            else:
                                baked_texture = bpy.data.images.load(full_image_path)
                            node_texture.image = baked_texture
                            baked_texture.reload()
                            print(f"Successfully auto-loaded: {clean_img_name}")
                            replaced_count += 1
                        except Exception as e:
                            print(f"Error loading image {clean_img_name}: {e}")

                else:
                    print("Could not auto-load texture: Blend file must be saved to determine folder path.")
                
                links.new(node_uvmap.outputs['UV'], node_texture.inputs['Vector'])
                links.new(node_texture.outputs['Color'], node_principled.inputs['Base Color'])
                links.new(node_texture.outputs['Alpha'], node_principled.inputs['Alpha'])
                links.new(node_principled.outputs['BSDF'], node_output.inputs['Surface'])

                obj.data.materials.append(new_mat)
        
        self.report({'INFO'}, f"Replaced materials in {replaced_count} objects...")
        return {'FINISHED'}
        
# ====================================================================
# Replace selected materials with baked materials where applicable
# ====================================================================
class OOTP_replace_selected_materials(bpy.types.Operator):
    """Replace selected materials with baked materials, where applicable"""
    bl_idname = "ootp.replace_selected_materials"
    bl_label = "Replace selected materials with baked textures"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        
        mesh_objects = [obj for obj in context.selected_objects if "nobake" not in obj.name.lower() and obj.type == 'MESH']
        mesh_objects = sorted(mesh_objects, key=lambda obj: obj.name.lower())
        
        replaced_count = 0
    
        for obj in mesh_objects:
            if "nobake" in obj.name.lower():
                continue
            
            if obj.type == 'MESH':
                obj_name = obj.name
                mat_name = obj_name[2:] if obj_name.startswith("C-") else obj_name
                
                obj.data.materials.clear()
        
                new_mat = bpy.data.materials.new(name=mat_name)
                new_mat.use_nodes = True
                nodes = new_mat.node_tree.nodes
                links = new_mat.node_tree.links
                
                nodes.clear()

                node_output  = nodes.new(type='ShaderNodeOutputMaterial')
                node_principled = nodes.new(type='ShaderNodeBsdfPrincipled')
                node_texture = nodes.new(type='ShaderNodeTexImage')
                node_uvmap   = nodes.new(type='ShaderNodeUVMap')
                
                node_uvmap.location = (-600, 0)
                node_texture.location = (-300, 0)
                node_principled.location = (0, 0)
                node_output.location = (300, 0)
                
                active_uv = obj.data.uv_layers.active
                if active_uv:
                    node_uvmap.uv_map = active_uv.name

                clean_img_name = f"{mat_name.replace(' ', '_')}_day.png"
                
                if bpy.data.is_saved:
                    absolute_blend_path = bpy.path.abspath(bpy.data.filepath)
                    blend_dir = os.path.dirname(absolute_blend_path)
                    full_image_path = os.path.join(blend_dir, clean_img_name)
                    
                    if os.path.exists(full_image_path):
                        try:
                            if clean_img_name in bpy.data.images:
                                baked_texture = bpy.data.images[clean_img_name]
                                
                                if baked_texture.packed_file:
                                    baked_texture.unpack(method='USE_LOCAL')
                                baked_texture.filepath = full_image_path
                            else:
                                baked_texture = bpy.data.images.load(full_image_path)
                            node_texture.image = baked_texture
                            baked_texture.reload()
                            print(f"Successfully auto-loaded: {clean_img_name}")
                            replaced_count += 1
                        except Exception as e:
                            print(f"Error loading image {clean_img_name}: {e}")

                else:
                    print("Could not auto-load texture: Blend file must be saved to determine folder path.")
                
                links.new(node_uvmap.outputs['UV'], node_texture.inputs['Vector'])
                links.new(node_texture.outputs['Color'], node_principled.inputs['Base Color'])
                links.new(node_texture.outputs['Alpha'], node_principled.inputs['Alpha'])
                links.new(node_principled.outputs['BSDF'], node_output.inputs['Surface'])

                obj.data.materials.append(new_mat)
        
        self.report({'INFO'}, f"Replaced materials in {replaced_count} objects...")
        return {'FINISHED'}
        
        
# ====================================================================
# OOTP OBJ export with crowd replacements
# ====================================================================        
class WM_OT_ootp_ballpark_exporter(bpy.types.Operator, ExportHelper):
    """Export OBJ for OOTP and automatically swap out crowd material blocks in the MTL file"""
    bl_idname = "wm.export_ootp_ballpark"
    bl_label = "Export OOTP Ballpark (.obj)"
    
    filename_ext = ".obj"
    filter_glob: bpy.props.StringProperty(default="*.obj", options={'HIDDEN'})

    def execute(self, context):
        obj_filepath = self.filepath
        export_dir = os.path.dirname(obj_filepath)
        mtl_filepath = obj_filepath.replace(".obj", ".mtl")
        
        for obj in context.scene.objects:
            if "nobake" in obj.name.lower() and obj.type == 'MESH':
                for slot in obj.material_slots:
                    if slot.material and slot.material.use_nodes:
                        for node in slot.material.node_tree.nodes:
                            if node.type == 'TEX_IMAGE' and node.image:
                                img = node.image
                                target_img_path = os.path.join(export_dir, os.path.basename(img.filepath))
                                
                                if img.packed_file:
                                    img.unpack(method='WRITE_LOCAL')
                                else:
                                    try:
                                        img.save_render(target_img_path)
                                    except Exception:
                                        pass
        
        for img in bpy.data.images:
            if img.is_dirty or img.source == 'GENERATED':                
                filename = img.name if img.name.lower().endswith(('.png', '.webp')) else f"{img.name}.png"               
                full_save_path = os.path.join(bake_directory, filename)                
                try:
                    img.save_render(full_save_path, scene=context.scene)                    
                    img.filepath = full_save_path
                    img.filepath_raw = full_save_path                    
                    print(f"Successfully flushed bake canvas to disk: {full_save_path}")
                except Exception as e:
                    print(f"Could not save image {img.name}: {e}")
                    
        bpy.ops.wm.obj_export(
            filepath=obj_filepath,
            export_selected_objects=False,   
            export_animation=False,
            export_materials=True,           
            export_pbr_extensions=False,     
            path_mode='COPY',
            forward_axis='NEGATIVE_Z',       
            up_axis='Y',
            export_triangulated_mesh=True   
        )
        
        if os.path.exists(mtl_filepath):
            try:
                with open(mtl_filepath, 'r', encoding='utf-8') as f:
                    mtl_content = f.read()

                replacements = [
                    # --- BLUE ---
                    {
                        "pattern": r"newmtl seating_attendance4_blue\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl seating_attendance4_blue\nKa 0.000000 0.000000 0.000000\nKd 0.380392 0.384314 0.364706\nKs 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity4_blue.jpg"
                    },
                    {
                        "pattern": r"newmtl seating_attendance3_blue\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl seating_attendance3_blue\nKa 0.000000 0.000000 0.000000\nKd 0.364706 0.376471 0.352941\nKs 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity3_blue.jpg"
                    },
                    {
                        "pattern": r"newmtl seating_attendance2_blue\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl seating_attendance2_blue\nKa 0.000000 0.000000 0.000000\nKd 0.345098 0.380392 0.415686\nKs 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity2_blue.jpg"
                    },
                    {
                        "pattern": r"newmtl seating_attendance1_blue\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl seating_attendance1_blue\nKa 0.000000 0.000000 0.000000\nKd 0.309804 0.360784 0.419608\nKs 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity1_blue.jpg"
                    },
                    
                    # --- RED ---
                    {
                        "pattern": r"newmtl seating_attendance4_red\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl seating_attendance4_red\nKa 0.000000 0.000000 0.000000\nKd 0.380392 0.384314 0.364706\nKs 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity4_red.jpg"
                    },
                    {
                        "pattern": r"newmtl seating_attendance3_red\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl seating_attendance3_red\nKa 0.000000 0.000000 0.000000\nKd 0.364706 0.376471 0.352941\nKs 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity3_red.jpg"
                    },
                    {
                        "pattern": r"newmtl seating_attendance2_red\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl seating_attendance2_red\nKa 0.000000 0.000000 0.000000\nKd 0.345098 0.380392 0.415686\nKs 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity2_red.jpg"
                    },
                    {
                        "pattern": r"newmtl seating_attendance1_red\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl seating_attendance1_red\nKa 0.000000 0.000000 0.000000\nKd 0.309804 0.360784 0.419608\nKs 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity1_red.jpg"
                    },

                    # --- GREY ---
                    {
                        "pattern": r"newmtl seating_attendance4_grey\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl seating_attendance4_grey\nKa 0.000000 0.000000 0.000000\nKd 0.380392 0.384314 0.364706\nKs 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity4_grey.jpg"
                    },
                    {
                        "pattern": r"newmtl seating_attendance3_grey\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl seating_attendance3_grey\nKa 0.000000 0.000000 0.000000\nKd 0.364706 0.376471 0.352941\nKs 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity3_grey.jpg"
                    },
                    {
                        "pattern": r"newmtl seating_attendance2_grey\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl seating_attendance2_grey\nKa 0.000000 0.000000 0.000000\nKd 0.345098 0.380392 0.415686\nKs 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity2_grey.jpg"
                    },
                    {
                        "pattern": r"newmtl seating_attendance1_grey\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl seating_attendance1_grey\nKa 0.000000 0.000000 0.000000\nKd 0.309804 0.360784 0.419608\nKs 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity1_grey.jpg"
                    },

                    # --- GREEN ---
                    {
                        "pattern": r"newmtl crowd_new_4\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl crowd_new_4\nKa 0.000000 0.000000 0.000000\nKd 0.380392 0.384314 0.364706\nKs 0.000000 0.000000 0.000000\nKe 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity4.jpg"
                    },
                    {
                        "pattern": r"newmtl Crowd_new_3\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl Crowd_new_3\nKa 0.000000 0.000000 0.000000\nKd 0.364706 0.376471 0.352941\nKs 0.000000 0.000000 0.000000\nKe 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity3.jpg"
                    },
                    {
                        "pattern": r"newmtl crowd_new_2\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl crowd_new_2\nKa 0.000000 0.000000 0.000000\nKd 0.321569 0.360784 0.309804\nKs 0.000000 0.000000 0.000000\nKe 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity2.jpg"
                    },
                    {
                        "pattern": r"newmtl crowd_new_1\b.*?(?=\n\n|\Z)",
                        "replacement": "newmtl crowd_new_1\nKa 0.000000 0.000000 0.000000\nKd 0.286275 0.349020 0.274510\nKs 0.000000 0.000000 0.000000\nKe 0.000000 0.000000 0.000000\nNi 1.000000\nd 1.000000\nillum 1\nmap_Kd ../../attendance/seating_popularity1.jpg"
                    }
                ]

                patch_count = 0
                for item in replacements:
                    if re.search(item["pattern"], mtl_content, flags=re.DOTALL):
                        mtl_content = re.sub(item["pattern"], item["replacement"], mtl_content, flags=re.DOTALL)
                        patch_count += 1

                with open(mtl_filepath, 'w', encoding='utf-8') as f:
                    f.write(mtl_content)
                    
                self.report({'INFO'}, f"Export complete. Successfully patched {patch_count} active definitions.")
                
            except Exception as e:
                self.report({'ERROR'}, f"Failed parsing MTL textures: {str(e)}")
        else:
            self.report({'WARNING'}, "OBJ Exported, but no tracking MTL found to override.")

        return {'FINISHED'}

# ====================================================================
# Bake all components that aren't tagged "nobake"
# ==================================================================== 
class OOTP_OT_batch_bake_day(bpy.types.Operator):
    """Bakes all valid and prepared components and saves them as either _day or _night bakes."""
    bl_idname = "ootp.batch_bake"
    bl_label = "OOTP Batch Bake"
    bl_options = {'REGISTER', 'UNDO'}
    
    max_samples: bpy.props.IntProperty(
        name="Max Cycles Samples",
        description="Set the sample count for the high-quality bake pass",
        default=128,
        min=1,
        max=4096
    )
    
    bake_time: bpy.props.EnumProperty(
        name="Lighting Setup",
        description="Choose the suffix for your final exported texture maps",
        items=[
            ('DAY', "Day Pass (_day)", "Bake full diffuse daylight illumination"),
            ('NIGHT', "Night Pass (_night)", "Bake full diffuse nighttime stadium lighting")
        ],
        default='DAY'
    )

    def invoke(self, context, event):
        # This forces Blender to pop up a dialog box asking for the properties
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        
        start_time = time.time()
        
        context.scene.render.engine = 'CYCLES'
        context.scene.cycles.samples = self.max_samples
        context.scene.render.bake.use_pass_direct = True
        context.scene.render.bake.use_pass_indirect = True
        context.scene.render.bake.use_pass_color = True
        
        suffix = "_day" if self.bake_time == 'DAY' else "_night"
        
        ensure_system_console_open()
        
        if not bpy.data.is_saved:
            self.report({'ERROR'}, "Please save your Blend file first so the script knows where to drop the textures!")
            return {'CANCELLED'}
            
        model_dir = os.path.dirname(bpy.data.filepath)
        
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')
            
        baked_count = 0
        
        mesh_objects = [
            obj for obj in context.scene.objects 
            if obj.type == 'MESH' 
            and "nobake" not in obj.name.lower() 
            and not obj.hide_viewport 
            and not obj.hide_render
        ]
        
        mesh_objects = sorted(mesh_objects, key=lambda obj: obj.name.lower())
        
        for idx, obj in enumerate(mesh_objects, start=1):
            
            if "nobake" in obj.name.lower() or obj.hide_viewport or obj.hide_render:
                print(f"({idx}/{len(mesh_objects)}) Skipping {obj.name}: Object is excluded, hidden or disabled for baking.")
                continue
                
            if obj.type == 'MESH':
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj
                
                target_image = None
                for slot in obj.material_slots:
                    if slot.material and slot.material.use_nodes:
                        for node in slot.material.node_tree.nodes:
                            if node.type == 'TEXT_IMAGE' or (node.type == 'TEX_IMAGE' and node.label == "Bake Target"):
                                if node.image:
                                    target_image = node.image
                                    node.select = True
                                    slot.material.node_tree.nodes.active = node
                
                if not target_image:
                    print(f"({idx}/{len(mesh_objects)}) Skipping {obj.name}: No active 'Bake Target' image node found.")
                    continue
                    
                print(f"({idx}/{len(mesh_objects)}) Baking {obj.name} at {self.max_samples} samples...")
                
                bpy.ops.object.bake(type='DIFFUSE', save_mode='INTERNAL')
                
                base_name, _ = os.path.splitext(target_image.name)
                modified_base = base_name.replace("_day", suffix)
                new_filename = f"{modified_base}.png"
                save_path = os.path.join(model_dir, new_filename)
                
                target_image.filepath_raw = save_path
                target_image.file_format = 'PNG'
                target_image.save()
                
                print(f"  -> Successfully saved: {save_path}")
                baked_count += 1
         
        
        elapsed_seconds = time.time() - start_time
        minutes = int(elapsed_seconds // 60)
        seconds = int(elapsed_seconds % 60)
        
        time_string = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
        
        self.report({'INFO'}, f"Successfully baked and saved {baked_count} texture maps in {time_string}")
        return {'FINISHED'}

# ====================================================================
# Bake selected components that aren't tagged "nobake"
# ==================================================================== 
class OOTP_OT_selected_batch_bake_day(bpy.types.Operator):
    """Bakes all valid and selected components and saves them as either _day or _night bakes."""
    bl_idname = "ootp.selected_batch_bake"
    bl_label = "OOTP Selected Batch Bake"
    bl_options = {'REGISTER', 'UNDO'}
    
    max_samples: bpy.props.IntProperty(
        name="Max Cycles Samples",
        description="Set the sample count for the high-quality bake pass",
        default=128,
        min=1,
        max=4096
    )
    
    bake_time: bpy.props.EnumProperty(
        name="Lighting Setup",
        description="Choose the suffix for your final exported texture maps",
        items=[
            ('DAY', "Day Pass (_day)", "Bake full diffuse daylight illumination"),
            ('NIGHT', "Night Pass (_night)", "Bake full diffuse nighttime stadium lighting")
        ],
        default='DAY'
    )

    def invoke(self, context, event):
        # This forces Blender to pop up a dialog box asking for the properties
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        
        start_time = time.time()
        
        context.scene.render.engine = 'CYCLES'
        context.scene.cycles.samples = self.max_samples
        context.scene.render.bake.use_pass_direct = True
        context.scene.render.bake.use_pass_indirect = True
        context.scene.render.bake.use_pass_color = True
        
        suffix = "_day" if self.bake_time == 'DAY' else "_night"
        
        ensure_system_console_open()
        
        if not bpy.data.is_saved:
            self.report({'ERROR'}, "Please save your Blend file first so the script knows where to drop the textures!")
            return {'CANCELLED'}
            
        model_dir = os.path.dirname(bpy.data.filepath)
        
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')
            
        baked_count = 0
        
        mesh_objects = [
            obj for obj in context.selected_objects 
            if obj.type == 'MESH' 
            and "nobake" not in obj.name.lower() 
            and not obj.hide_viewport 
            and not obj.hide_render
        ]
        
        mesh_objects = sorted(mesh_objects, key=lambda obj: obj.name.lower())
        
        for idx, obj in enumerate(mesh_objects, start=1):
            
            if "nobake" in obj.name.lower() or obj.hide_viewport or obj.hide_render:
                print(f"({idx}/{len(mesh_objects)}) Skipping {obj.name}: Object is excluded, hidden or disabled for baking.")
                continue
                
            if obj.type == 'MESH':
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj
                
                target_image = None
                for slot in obj.material_slots:
                    if slot.material and slot.material.use_nodes:
                        for node in slot.material.node_tree.nodes:
                            if node.type == 'TEXT_IMAGE' or (node.type == 'TEX_IMAGE' and node.label == "Bake Target"):
                                if node.image:
                                    target_image = node.image
                                    node.select = True
                                    slot.material.node_tree.nodes.active = node
                
                if not target_image:
                    print(f"({idx}/{len(mesh_objects)}) Skipping {obj.name}: No active 'Bake Target' image node found.")
                    continue
                    
                print(f"({idx}/{len(mesh_objects)}) Baking {obj.name} at {self.max_samples} samples...")
                
                bpy.ops.object.bake(type='DIFFUSE', save_mode='INTERNAL')
                
                base_name, _ = os.path.splitext(target_image.name)
                modified_base = base_name.replace("_day", suffix)
                new_filename = f"{modified_base}.png"
                save_path = os.path.join(model_dir, new_filename)
                
                target_image.filepath_raw = save_path
                target_image.file_format = 'PNG'
                target_image.save()
                
                print(f"  -> Successfully saved: {save_path}")
                baked_count += 1
         
        
        elapsed_seconds = time.time() - start_time
        minutes = int(elapsed_seconds // 60)
        seconds = int(elapsed_seconds % 60)
        
        time_string = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
        
        self.report({'INFO'}, f"Successfully baked and saved {baked_count} texture maps in {time_string}")
        return {'FINISHED'}
  
# ====================================================================
# Open config json file for editing
# ==================================================================== 

class OOTP_open_config(bpy.types.Operator):
    """Open the custom defaults JSON file in your default text editor"""
    bl_idname = "ootp.open_config"
    bl_label = "Edit Add-on Defaults File"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Ensure the file exists before opening it
        if not os.path.exists(CONFIG_FILE_PATH):
            load_user_defaults()
            
        # Blender's native cross-platform tool to open files/folders externally
        bpy.ops.wm.url_open(url=CONFIG_FILE_PATH)
        
        self.report({'INFO'}, f"Opened config file: {os.path.basename(CONFIG_FILE_PATH)}")
        return {'FINISHED'}

# ====================================================================
# Reload preferences
# ==================================================================== 

class OOTP_reload_config(bpy.types.Operator):
    """Reload settings from the defaults JSON file without restarting Blender"""
    bl_idname = "ootp.reload_config"
    bl_label = "Reload Add-on Settings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        global USER_SETTINGS
        
        # Re-run your loading function to refresh the global cache
        USER_SETTINGS = load_user_defaults()
        
        # Push a visual notification toast to the bottom right of Blender's UI
        self.report({'INFO'}, "Add-on settings reloaded successfully!")
        return {'FINISHED'}
        
# ====================================================================
# Reload preferences
# ==================================================================== 

class OOTP_day_night_toggle(bpy.types.Operator):
    """Toggle Between Day and Night Lighting"""
    bl_idname = "ootp.day_night_toggle"
    bl_label = "Switch Between Day and Night Lighting"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        world = bpy.context.scene.world
        if not world or not world.node_tree:
            print("No active world node tree found.")
            return
        
        nodes = world.node_tree.nodes
        node_sky = next((n for n in nodes if n.type == 'TEX_SKY'), None)
        node_background = next((n for n in nodes if n.type == 'BACKGROUND'), None)
        
        if not node_sky or not node_background:
            set_default_sky_texture(world)
            return
        
        sky_data = USER_SETTINGS.get("sky_texture_defaults", {})
        
        if node_sky.sun_intensity > 0.05:
            node_sky.sun_intensity = 0.000             
            node_sky.sun_elevation = math.radians(0)  
            node_sky.sun_rotation = math.radians(90)
            node_background.inputs['Strength'].default_value = 0.100 
            night = True
            print("Sky set to night.")
        else:
            node_sky.sun_intensity = sky_data.get('sun_intensity')
            node_sky.sun_elevation = math.radians(sky_data.get('sun_elevation'))   
            node_sky.sun_rotation = math.radians(sky_data.get('sun_rotation'))  
            node_background.inputs['Strength'].default_value = sky_data.get('strength')
            night = False
            print("Sky set to day.")
            
        material_brightness_map = {}
        
        emission_data = USER_SETTINGS.get("material_emission_defaults", {})
        
        for mat in bpy.data.materials:
            if not mat.node_tree:
                continue
                
            matched_keyword = None
            for keyword in emission_data.keys():
                if keyword in mat.name:
                    matched_keyword = keyword
                    break

            if matched_keyword:
                emission_strength = emission_data[matched_keyword] if night else 0.0
                
                mat_nodes = mat.node_tree.nodes
                principled = next((n for n in mat_nodes if n.type == 'BSDF_PRINCIPLED'), None)
                
                if principled:
                    if 'Emission Strength' in principled.inputs:
                        principled.inputs['Emission Strength'].default_value = emission_strength
                    print(f"{mat.name} strength set to {emission_strength}")
                    continue
                    
        return {'FINISHED'}
   
# ====================================================================
# UI MENU
# ====================================================================
class VIEW3D_MT_ootp_custom_menu(bpy.types.Menu):
    bl_label = "OOTP"
    bl_idname = "VIEW3D_MT_ootp_custom_menu"

    def draw(self, context):
        layout = self.layout
        
        layout.operator("ootp.scene_cleaner", text="Prepare Model", icon='FILE_REFRESH')
        layout.operator("ootp.object_cleaner", text="Prepare Selected Objects", icon='FILE_REFRESH')
        layout.operator("ootp.node_cloner", text="Clone Nodes to Component Materials", icon='DUPLICATE')
        layout.separator()
        layout.operator("ootp.global_unwrap", text="Unwrap Entire Model", icon='STICKY_UVS_LOC')
        layout.operator("ootp.selected_unwrap", text="Unwrap Selected Objects", icon='STICKY_UVS_LOC')
        layout.separator()
        layout.operator("ootp.batch_bake", text="Bake All Bakeable Components", icon='RENDER_STILL')
        layout.operator("ootp.selected_batch_bake", text="Bake Selected Components", icon='RENDER_STILL')
        layout.separator()
        layout.operator("ootp.replace_all_materials", text="Replace all materials with baked textures", icon='MATERIAL')
        layout.operator("ootp.replace_selected_materials", text="Replace selected materials with baked textures", icon='MATERIAL')
        layout.operator("ootp.day_night_toggle", text="Toggle between Day & Night Lighting", icon='LIGHT_SUN')
        layout.separator()
        layout.operator("wm.export_ootp_ballpark", text="Export Ballpark to OOTP", icon='EXPORT')
        layout.separator()
        layout.operator("ootp.open_config", text="Open config file", icon='CURRENT_FILE')
        layout.operator("ootp.reload_config", text="Reload preferences from config file", icon='LOOP_BACK')


def draw_menu_header(self, context):
    if context.mode == 'OBJECT':
        layout = self.layout
        layout.menu("VIEW3D_MT_ootp_custom_menu")

def register():
    global USER_SETTINGS
    USER_SETTINGS = load_user_defaults()
    bpy.utils.register_class(OOTP_OT_scene_cleaner)
    bpy.utils.register_class(OOTP_selected_scene_cleaner)
    bpy.utils.register_class(OOTP_OT_node_cloner)
    bpy.utils.register_class(OOTP_UV_unwrap_global)
    bpy.utils.register_class(OOTP_UV_unwrap_selected)
    bpy.utils.register_class(OOTP_replace_all_materials)
    bpy.utils.register_class(OOTP_replace_selected_materials)
    bpy.utils.register_class(WM_OT_ootp_ballpark_exporter)
    bpy.utils.register_class(OOTP_OT_batch_bake_day)
    bpy.utils.register_class(OOTP_OT_selected_batch_bake_day)
    bpy.utils.register_class(OOTP_open_config)
    bpy.utils.register_class(OOTP_reload_config)
    bpy.utils.register_class(OOTP_day_night_toggle)
    bpy.utils.register_class(VIEW3D_MT_ootp_custom_menu)
    bpy.types.VIEW3D_MT_editor_menus.append(draw_menu_header)

def unregister():
    bpy.types.VIEW3D_MT_editor_menus.remove(draw_menu_header)
    bpy.utils.unregister_class(VIEW3D_MT_ootp_custom_menu)
    bpy.utils.unregister_class(OOTP_OT_batch_bake_day)
    bpy.utils.unregister_class(OOTP_OT_selected_batch_bake_day)
    bpy.utils.unregister_class(WM_OT_ootp_ballpark_exporter)
    bpy.utils.unregister_class(OOTP_replace_all_materials)
    bpy.utils.unregister_class(OOTP_replace_selected_materials)
    bpy.utils.unregister_class(OOTP_UV_unwrap_global)
    bpy.utils.unregister_class(OOTP_UV_unwrap_selected)
    bpy.utils.unregister_class(OOTP_OT_node_cloner)
    bpy.utils.unregister_class(OOTP_selected_scene_cleaner)
    bpy.utils.unregister_class(OOTP_OT_scene_cleaner)
    bpy.utils.unregister_class(OOTP_open_config)
    bpy.utils.unregister_class(OOTP_reload_config)
    bpy.utils.unregister_class(OOTP_day_night_toggle)

if __name__ == "__main__":
    register()
    bpy.ops.ootp.batch_bake_day('INVOKE_DEFAULT')
