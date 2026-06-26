bl_info = {
    "name": "OOTP Ballpark Toolkit",
    "author": "Eriq Jaffe",
    "version": (0, 4),
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
from bpy_extras.io_utils import ExportHelper

def ensure_system_console_open():
    """Ensures the Windows system console is open without accidentally toggling it closed."""
    if sys.platform == 'win32':
        import ctypes
        
        # Get the handle of the console window associated with Blender
        # If no console is attached, this returns 0 (Null)
        console_handle = ctypes.windll.kernel32.GetConsoleWindow()
        
        # Also check if the window is currently visible to the user
        is_visible = ctypes.windll.user32.IsWindowVisible(console_handle) if console_handle else False
        
        # If the console window handle doesn't exist, or it exists but is hidden, safely turn it on
        if not console_handle or not is_visible:
            try:
                bpy.ops.wm.console_toggle()
            except Exception as e:
                print(f"Failed to toggle console: {e}")


# ====================================================================
# OPERATOR 1: Global Scene Cleanup (Renamed Class & ID)
# ====================================================================
class OOTP_OT_scene_cleaner(bpy.types.Operator):
    """Purge DefaultMaterial geometry and isolate valid textures globally"""
    bl_idname = "ootp.scene_cleaner"
    bl_label = "Clean Scene & Isolate Materials"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        mesh_count = 0
        for obj in context.scene.objects:
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
                clean_img_name = f"{display_name.replace(' ', '_')}_bake"
                if clean_img_name not in bpy.data.images:
                    bake_image = bpy.data.images.new(
                        name=clean_img_name,
                        width=1024,
                        height=1024,
                        alpha=True
                    )
                    bake_image.generated_color = (0.0, 0.0, 0.0, 0.0)
                else:
                    bake_image = bpy.data.images[clean_img_name]

                # Add and Wire Shader Bake Nodes
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
# OPERATOR 2: Node Cloner (Renamed Class & ID to bypass cache)
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
# OPERATOR 3: Replace all materials with baked materials where applicable
# ====================================================================

class OOTP_replace_all_materials(bpy.types.Operator):
    """Replace all materials with baked materials, where applicable"""
    bl_idname = "ootp.replace_all_materials"
    bl_label = "Replace all materials with baked textures"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        
        mesh_objects = [obj for obj in context.scene.objects if "nobake" not in obj.name.lower() and obj.type == 'MESH']
        mesh_objects = sorted(mesh_objects, key=lambda obj: obj.name.lower())
    
        for obj in mesh_objects:
            if "nobake" in obj.name.lower():
                continue
            
            if obj.type == 'MESH':
                #mesh_count += 1
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
                    blend_dir = os.path.dirname(bpy.data.filepath)
                    # Combine the folder path with your clean image name
                    full_image_path = os.path.join(blend_dir, clean_img_name)
                    
                    # 3. Check if the file actually exists on your hard drive before loading
                    if os.path.exists(full_image_path):
                        try:
                            # Load the image safely into the texture node
                            baked_texture = bpy.data.images.load(full_image_path, check_existing=True)
                            node_texture.image = baked_texture
                            print(f"Successfully auto-loaded: {clean_img_name}")
                        except Exception as e:
                            print(f"Error loading image {clean_img_name}: {e}")
                    else:
                        # Fails gracefully without breaking the rest of your material setup script
                        print(f"Skipped loading: {clean_img_name} not found in blend folder.")
                else:
                    print("Could not auto-load texture: Blend file must be saved to determine folder path.")
                
                links.new(node_uvmap.outputs['UV'], node_texture.inputs['Vector'])
                links.new(node_texture.outputs['Color'], node_principled.inputs['Base Color'])
                links.new(node_principled.outputs['BSDF'], node_output.inputs['Surface'])

                obj.data.materials.append(new_mat)
        
        self.report({'INFO'}, f"I think I replaced as many textres as I could find...")
        return {'FINISHED'}
        
# ====================================================================
# OPERATOR 4: OOTP OBJ export with crowd replacements
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
                            # Find image texture nodes
                            if node.type == 'TEX_IMAGE' and node.image:
                                img = node.image
                                # Determine the target path inside the export folder
                                target_img_path = os.path.join(export_dir, os.path.basename(img.filepath))
                                
                                # If the image is packed inside Blender, unpack it directly to our folder
                                if img.packed_file:
                                    img.unpack(method='WRITE_LOCAL')
                                # If it's a virtual/cached path, save a real copy out to disk
                                else:
                                    try:
                                        img.save_render(target_img_path)
                                    except Exception:
                                        # Fallback if save_render fails
                                        pass
        
        bpy.ops.wm.obj_export(
            filepath=obj_filepath,
            export_selected_objects=False,  # Set to True if you only want selected exported
            export_animation=False,
            export_pbr_extensions=False,    # Keeps standard MTL format readable by OOTP
            path_mode='COPY',               
            forward_axis='NEGATIVE_Z',       
            up_axis='Y',
            export_triangulated_mesh=True   # Locks in the triangulated faces auto-fix
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
# OPERATOR 5: Bake all components that aren't tagged "nobake"
# ==================================================================== 
class OOTP_OT_batch_bake_day(bpy.types.Operator):
    """Bakes all valid and prepared components and saves them as either _day or _night bakes."""
    bl_idname = "ootp.batch_bake"
    bl_label = "OOTP Batch Bake"
    bl_options = {'REGISTER', 'UNDO'}
    
    # This creates the user input field in the Blender popup dialog box
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
        
        # 1. Ensure we are using Cycles and set the user-defined sample rate
        context.scene.render.engine = 'CYCLES'
        context.scene.cycles.samples = self.max_samples
        
        # Ensure Diffuse bake options only focus on flat Color (no direct/indirect lighting)
        context.scene.render.bake.use_pass_direct = True
        context.scene.render.bake.use_pass_indirect = True
        context.scene.render.bake.use_pass_color = True
        
        suffix = "_day" if self.bake_time == 'DAY' else "_night"
        
        ensure_system_console_open()
        
        # Determine the export directory based on your current blend file location
        if not bpy.data.is_saved:
            self.report({'ERROR'}, "Please save your Blend file first so the script knows where to drop the textures!")
            return {'CANCELLED'}
            
        model_dir = os.path.dirname(bpy.data.filepath)
        
        # Force Object Mode
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
        
        # 2. Loop through all components in the scene
        for obj in mesh_objects:
            
            if "nobake" in obj.name.lower() or obj.hide_viewport or obj.hide_render:
                print(f"Skipping {obj.name}: Object is excluded, hidden or disabled for baking.")
                continue
                
            if obj.type == 'MESH':
                # Isolate selection to the single object so Cycles focuses the bake
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj
                
                # Double check that our target image node exists and is active
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
                    print(f"Skipping {obj.name}: No active 'Bake Target' image node found.")
                    continue
                    
                print(f"Baking {obj.name} at {self.max_samples} samples...")
                
                # 3. Trigger the Cycles Texture Bake
                bpy.ops.object.bake(type='DIFFUSE', save_mode='INTERNAL')
                
                # 4. Save and rename the resulting image map asset
                new_filename = target_image.name.replace("_bake", suffix) + ".png"
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
        
        self.report({'INFO'}, f"Successfully baked and saved {baked_count} day texture maps in {time_string}")
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
        layout.operator("ootp.node_cloner", text="Clone Nodes to Component Materials", icon='DUPLICATE')
        layout.separator()
        layout.operator("ootp.batch_bake", text="Bake All Bakeable Components", icon='RENDER_STILL')
        layout.separator()
        layout.operator("ootp.replace_all_materials", text="Replace all materials with baked textures", icon='MATERIAL')
        layout.separator()
        layout.operator("wm.export_ootp_ballpark", text="Export Ballpark to OOTP", icon='EXPORT')


def draw_menu_header(self, context):
    if context.mode == 'OBJECT':
        layout = self.layout
        layout.menu("VIEW3D_MT_ootp_custom_menu")

def register():
    bpy.utils.register_class(OOTP_OT_scene_cleaner)
    bpy.utils.register_class(OOTP_OT_node_cloner)
    bpy.utils.register_class(OOTP_replace_all_materials)
    bpy.utils.register_class(WM_OT_ootp_ballpark_exporter)
    bpy.utils.register_class(OOTP_OT_batch_bake_day)
    bpy.utils.register_class(VIEW3D_MT_ootp_custom_menu)
    bpy.types.VIEW3D_MT_editor_menus.append(draw_menu_header)

def unregister():
    bpy.types.VIEW3D_MT_editor_menus.remove(draw_menu_header)
    bpy.utils.unregister_class(VIEW3D_MT_ootp_custom_menu)
    bpy.utils.unregister_class(OOTP_OT_batch_bake_day)
    bpy.utils.unregister_class(WM_OT_ootp_ballpark_exporter)
    bpy.utils.unregister_class(OOTP_replace_all_materials)
    bpy.utils.unregister_class(OOTP_OT_node_cloner)
    bpy.utils.unregister_class(OOTP_OT_scene_cleaner)

if __name__ == "__main__":
    register()
    bpy.ops.ootp.batch_bake_day('INVOKE_DEFAULT')