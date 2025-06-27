"""
Gemini Integration Utility
Handles integration of Gemini LLM results into seraphine structure
"""
from .helpers import debug_print

def integrate_gemini_results(seraphine_analysis, gemini_results):
    """
    Integrate Gemini results into seraphine structure at individual bbox level
    """
    if not gemini_results or not gemini_results.get('images'):
        debug_print("⚠️  No Gemini results to integrate")
        return seraphine_analysis
    
    debug_print("\n🔗 Integrating Gemini results into seraphine structure...")
    
    # Create mapping from ALL Gemini results across all images
    id_to_gemini = {}
    
    for image_result in gemini_results['images']:
        if image_result['analysis_success'] and image_result.get('icons'):
            for icon in image_result['icons']:
                icon_id = icon.get('id')  # Like "H1_1", "H12_3", etc.
                if icon_id:
                    id_to_gemini[icon_id] = {
                        'icon_name': icon.get('name', 'unknown'),
                        'brief': icon.get('usage', 'No description'),
                        'enabled': icon.get('enabled', True),
                        'interactive': icon.get('interactive', True),
                        'type': icon.get('type', 'icon')  # New field
                    }
    
    debug_print(f"   📋 Found {len(id_to_gemini)} Gemini mappings to integrate")
    
    # Integrate results into seraphine bbox_processor
    bbox_processor = seraphine_analysis['bbox_processor']
    total_integrated = 0
    
    for group_id, boxes in bbox_processor.final_groups.items():
        # Process each box in the group
        for i, bbox in enumerate(boxes):
            item_id = f"{group_id}_{i+1}"  # H1_1, H1_2, etc.
            
            if item_id in id_to_gemini:
                # Found exact match!
                gemini_data = id_to_gemini[item_id]
                bbox.g_icon_name = gemini_data['icon_name']
                bbox.g_brief = gemini_data['brief']
                bbox.g_enabled = gemini_data['enabled']
                bbox.g_interactive = gemini_data['interactive']
                bbox.g_type = gemini_data['type']  # New field
                total_integrated += 1
                
                if total_integrated <= 5:  # Show first 5 for debugging
                    debug_print(f"   ✅ {item_id}: '{gemini_data['icon_name']}' - {gemini_data['brief'][:50]}...")
            else:
                # Default values if no Gemini result available
                bbox.g_icon_name = 'unanalyzed'
                bbox.g_brief = 'Not analyzed by Gemini'
    
    debug_print(f"✅ Integrated Gemini results: {total_integrated}/{sum(len(boxes) for boxes in bbox_processor.final_groups.values())} items updated")
    
    # 🎯 NEW: REGENERATE SERAPHINE_GEMINI_GROUPS WITH UPDATED DATA
    from .pipeline_exporter import create_enhanced_seraphine_structure
    
    # Get the merged_detections from analysis for proper ID lookup
    merged_detections = seraphine_analysis.get('original_merged_detections', [])
    
    # Create the enhanced structure with integrated Gemini data
    seraphine_gemini_groups = create_enhanced_seraphine_structure(
        seraphine_analysis, 
        merged_detections
    )
    
    # Add it to the analysis
    seraphine_analysis['seraphine_gemini_groups'] = seraphine_gemini_groups
    
    debug_print(f"🎯 Generated seraphine_gemini_groups with {len(seraphine_gemini_groups)} groups")
    
    return seraphine_analysis

async def run_gemini_analysis(seraphine_analysis, grouped_image_paths, image_path, config):
    """
    Run Gemini LLM analysis with optimized image sharing
    """
    if not config.get("gemini_enabled", False):
        debug_print("\n⏭️  Gemini analysis disabled in config")
        return None
    
    debug_print("\n🤖 Step 4: Gemini LLM Analysis (Optimized Image Sharing)")
    debug_print("=" * 70)
    
    try:
        from .gemini_analyzer import GeminiIconAnalyzer
        import os
        
        output_dir = config.get("output_dir", "outputs")
        filename_base = os.path.splitext(os.path.basename(image_path))[0]
        
        # Initialize analyzer - let it use default prompt path (relative to module)
        analyzer = GeminiIconAnalyzer(
            prompt_path=config.get("gemini_prompt_path"),  # Pass None to use default
            output_dir=output_dir,
            max_concurrent_requests=config.get("gemini_max_concurrent", 4),
            save_results=config.get("save_gemini_json", True)
        )
        
        # Use direct image mode for optimized sharing
        if config.get("gemini_return_images_b64", True):
            debug_print("   📸 Using optimized direct image mode (faster, less I/O)")
            
            from .seraphine_generator import FinalGroupImageGenerator
            
            # Create generator to get direct images
            final_group_generator = FinalGroupImageGenerator(
                output_dir=output_dir,
                save_mapping=False  # Don't save files, just get images
            )
            
            # Get direct images using the correct method
            result = final_group_generator.create_grouped_images(
                image_path=image_path,
                seraphine_analysis=seraphine_analysis,
                filename_base=filename_base,
                return_direct_images=True
            )
            
            # Extract direct images from result
            direct_images = result['direct_images']
            
            debug_print(f"   🖼️  Generated {len(direct_images)} direct images for Gemini analysis")
            
            # Analyze with direct images (no file I/O)
            gemini_results = await analyzer.analyze_grouped_images(
                grouped_image_paths=None,
                filename_base=filename_base,
                direct_images=direct_images
            )
        else:
            debug_print("   📁 Using file mode (traditional)")
            # Use traditional file mode
            gemini_results = await analyzer.analyze_grouped_images(
                grouped_image_paths=grouped_image_paths,
                filename_base=filename_base,
                direct_images=None
            )
        
        debug_print(f"✅ Gemini analysis complete:")
        debug_print(f"   🖼️  Analyzed: {gemini_results['successful_analyses']}/{gemini_results['total_images_analyzed']} images")
        debug_print(f"   🎯 Total icons found: {gemini_results['total_icons_found']}")
        debug_print(f"   ⏱️  Analysis time: {gemini_results['analysis_duration_seconds']:.2f}s")
        
        return gemini_results
        
    except ImportError:
        debug_print("❌ Gemini analyzer not available (missing dependencies)")
        return None
    except Exception as e:
        debug_print(f"❌ Gemini analysis failed: {str(e)}")
        return None
