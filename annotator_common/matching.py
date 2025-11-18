"""
Fuzzy matching utilities for comparing product and cutout analyses.

This module provides functions to calculate weighted similarity scores between
product images and cutout analyses, enabling robust matching even when LLM
analysis is imperfect.
"""

import json
from difflib import SequenceMatcher
from typing import Dict, List, Tuple, Optional


def get_similarity_ratio(str1: str, str2: str) -> float:
    """
    Calculate similarity ratio between two strings using SequenceMatcher.
    
    Args:
        str1: First string
        str2: Second string
        
    Returns:
        Similarity ratio between 0.0 (no match) and 1.0 (exact match)
    """
    if not str1 or not str2:
        return 0.0
    return SequenceMatcher(None, str1, str2).ratio()


def extract_key_fields(analysis: Dict) -> Dict[str, str]:
    """
    Extract key fields from analysis for comparison.
    
    Handles different possible field name variations in the analysis structure.
    
    Args:
        analysis: Analysis dictionary (product or cutout)
        
    Returns:
        Dictionary with normalized field names:
        - brand
        - product_name
        - color_combined
        - visible_text
        - material
        - json_string
    """
    brand = ""
    product_name = ""
    color_combined = ""
    visible_text = ""
    material = ""
    json_string = ""
    
    if isinstance(analysis, dict):
        # Handle case where analysis is wrapped in "analysis" string (unparsed JSON)
        if "analysis" in analysis and isinstance(analysis["analysis"], str):
            try:
                parsed_analysis = json.loads(analysis["analysis"])
                if isinstance(parsed_analysis, dict):
                    analysis = parsed_analysis
            except (json.JSONDecodeError, ValueError):
                pass  # Keep original analysis if parsing fails
        
        # Try different possible field names
        brand = (
            analysis.get("brand_name") or 
            analysis.get("brand") or 
            analysis.get("analysis_result", {}).get("brand", "")
        )
        product_name = (
            analysis.get("product_name") or 
            analysis.get("product") or 
            analysis.get("analysis_result", {}).get("product_name", "")
        )
        
        # Extract colors - combine primary and secondary
        color_primary = analysis.get("color_primary") or analysis.get("colors_primary_secondary", {}).get("primary", "")
        color_secondary = analysis.get("colors_secondary")
        if isinstance(color_secondary, dict):
            color_secondary = " ".join(str(v) for v in color_secondary.values() if v)
        elif isinstance(color_secondary, (list, tuple)):
            color_secondary = " ".join(str(v) for v in color_secondary)
        
        color_combined = f"{color_primary} {color_secondary}".strip()
        
        # Extract visible text
        visible_text = analysis.get("visible_text", "")
        
        # Extract material
        material_obj = analysis.get("material", {})
        if isinstance(material_obj, dict):
            material = " ".join(str(v) for v in material_obj.values() if v)
        else:
            material = str(material_obj) if material_obj else ""
        
        # Convert entire analysis to JSON string for comparison
        json_string = json.dumps(analysis, ensure_ascii=False, sort_keys=True)
    
    return {
        "brand": str(brand) if brand else "",
        "product_name": str(product_name) if product_name else "",
        "color_combined": str(color_combined) if color_combined else "",
        "visible_text": str(visible_text) if visible_text else "",
        "material": str(material) if material else "",
        "json_string": str(json_string) if json_string else ""
    }


def calculate_weighted_similarity(product_fields: Dict[str, str], cutout_fields: Dict[str, str]) -> Dict:
    """
    Calculate weighted similarity between product and cutout fields.
    
    Args:
        product_fields: Extracted fields from product analysis
        cutout_fields: Extracted fields from cutout analysis
        
    Returns:
        Dictionary containing:
        - overall_similarity: Weighted average similarity (0.0 to 1.0)
        - brand_similarity
        - product_similarity
        - color_similarity
        - visible_text_similarity
        - material_similarity
        - json_similarity
    """
    # Calculate similarity for brand and product_name
    brand_similarity = get_similarity_ratio(
        product_fields["brand"].lower(),
        cutout_fields["brand"].lower()
    )
    
    product_similarity = get_similarity_ratio(
        product_fields["product_name"].lower(),
        cutout_fields["product_name"].lower()
    )
    
    # Calculate similarity for additional fields
    color_similarity = get_similarity_ratio(
        product_fields["color_combined"].lower(),
        cutout_fields["color_combined"].lower()
    ) if product_fields["color_combined"] and cutout_fields["color_combined"] else 0.0
    
    visible_text_similarity = get_similarity_ratio(
        product_fields["visible_text"].lower(),
        cutout_fields["visible_text"].lower()
    ) if product_fields["visible_text"] and cutout_fields["visible_text"] else 0.0
    
    material_similarity = get_similarity_ratio(
        product_fields["material"].lower(),
        cutout_fields["material"].lower()
    ) if product_fields["material"] and cutout_fields["material"] else 0.0
    
    json_similarity = get_similarity_ratio(
        product_fields["json_string"],
        cutout_fields["json_string"]
    ) if product_fields["json_string"] and cutout_fields["json_string"] else 0.0
    
    # Weighted average similarity (brand and product most important)
    overall_similarity = (
        brand_similarity * 0.25 +
        product_similarity * 0.25 +
        color_similarity * 0.15 +
        visible_text_similarity * 0.15 +
        material_similarity * 0.10 +
        json_similarity * 0.10
    )
    
    return {
        "overall_similarity": overall_similarity,
        "brand_similarity": brand_similarity,
        "product_similarity": product_similarity,
        "color_similarity": color_similarity,
        "visible_text_similarity": visible_text_similarity,
        "material_similarity": material_similarity,
        "json_similarity": json_similarity
    }


def count_high_matches(similarity_data: Dict, threshold: float = 0.7) -> int:
    """
    Count how many similarity parameters are above the threshold.
    
    Args:
        similarity_data: Dictionary with similarity scores (from calculate_weighted_similarity)
        threshold: Threshold for considering a match "high" (default: 0.7)
        
    Returns:
        Number of parameters with similarity > threshold
    """
    similarities = [
        similarity_data.get('brand_similarity', 0.0),
        similarity_data.get('product_similarity', 0.0),
        similarity_data.get('color_similarity', 0.0),
        similarity_data.get('visible_text_similarity', 0.0),
        similarity_data.get('material_similarity', 0.0),
        similarity_data.get('json_similarity', 0.0)
    ]
    return sum(1 for s in similarities if s > threshold)


def find_best_match(cutout_analysis: Dict, product_analyses: List[Dict]) -> Optional[Tuple[float, Dict, Dict]]:
    """
    Find the best matching product for a cutout analysis.
    
    Args:
        cutout_analysis: Cutout analysis dictionary
        product_analyses: List of product analysis dictionaries
        
    Returns:
        Tuple of (similarity_score, similarity_data, product_analysis) for best match,
        or None if no products provided
    """
    if not product_analyses:
        return None
    
    # Extract cutout fields
    cutout_fields = extract_key_fields(cutout_analysis)
    
    best_score = -1.0
    best_similarity_data = None
    best_product = None
    
    for product in product_analyses:
        # Extract product fields (handle nested analysis structure)
        product_analysis_data = product.get("analysis", {})
        product_fields = extract_key_fields(product_analysis_data)
        
        # Calculate weighted similarity
        similarity_data = calculate_weighted_similarity(product_fields, cutout_fields)
        similarity_score = similarity_data["overall_similarity"]
        
        # Track best match
        if similarity_score > best_score:
            best_score = similarity_score
            best_similarity_data = similarity_data
            best_product = product
    
    # Return best match if found
    if best_product is not None:
        return (best_score, best_similarity_data, best_product)
    
    return None

