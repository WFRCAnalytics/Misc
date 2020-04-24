# -*- coding: utf-8 -*-
"""
Created on Fri Apr 24 12:22:01 2020

@author: jreynolds
"""


import arcpy
import os
import glob
arcpy.env.overwriteOutput = True

"""
Dissolve WFRC/MAG model area TAZ polygons into single model area polygon

Feature to line with model area outline polygon to create model area polyline (outline)

Select all roads in Utah, SL, Davis, Weber, and Box Elder counties that are not 'negative direction" of divided highways and not ramps or part of ramp systems
(not (DOT_RTNAME like '%N' or char_length(DOT_RTNAME >5)) and (County_L = '49003' or County_L = '49011' or County_L = '49035' or County_L = '49049' or County_L = '49057')

Append selected roads into feature class with model area polyline created in step #2

Features to polygons with appended set of roads + outline to create 'preliminary blocks'

Add a part count and Use Calculate Geometry to set values = to # of parts

Eliminate contained parts from 'preliminary blocks'

Create a 'filled blocks' section layer where part count (set earlier) was set to a number > 1

Select by location the 'preliminary blocks' (target) that intersect with 'filled blocks' (might have to use have centroid within)

Delete the selected preliminary blocks and then append the filled blocks layer 

add TAZ ID to microzone using centroid probably
"""
#==========================
# Args
#==========================

taz_polygons =os.path.join(os.getcwd(), 'Data\TAZ_geometry.shp') 
roads = r'E:\Data\Roads.shp'
temp_dir = os.path.join(os.getcwd(), 'Output')
delete_intermediate_layers = True

#==========================
# Create Preliminary Zones
#========================== 

print("Creating preliminary zones...")

# Dissolve TAZ features into one polygon
taz_dissolved = arcpy.Dissolve_management(taz_polygons, os.path.join(temp_dir, 'taz_dissolved.shp'))

# Get TAZ outline
taz_outline = arcpy.FeatureToLine_management(taz_dissolved, os.path.join(temp_dir, 'taz_outline.shp')) 

# Select roads that are (in either Salt Lake, Utah, Davis, Weber, or Box Elder County), not highway ramps, and limit double lane highway features to one line
roads_layer = arcpy.MakeFeatureLayer_management(roads, 'roads')
query = """CHAR_LENGTH( "DOT_RTNAME") <= 5  AND NOT "DOT_RTNAME" LIKE '%N' AND ("COUNTY_L" = '49003' OR "COUNTY_L"  = '49011' OR "COUNTY_L" = '49035'  OR "COUNTY_L" = '49049' OR "COUNTY_L" =  '49057')"""
arcpy.SelectLayerByAttribute_management(roads_layer, "NEW_SELECTION", query)

# Clip roads by taz boundary
roads_clipped = arcpy.Clip_analysis(roads_layer, taz_dissolved, os.path.join(temp_dir, 'roads_clipped.shp'))

# Merge roads with taz outline 
merged_roads = arcpy.Merge_management([roads_clipped, taz_outline], os.path.join(temp_dir, 'roads_plus_taz_outline.shp'))

# Create zones using feature to polygon tool
prelim_zones = arcpy.FeatureToPolygon_management(merged_roads, os.path.join(temp_dir,"prelim_zones.shp"))

#========================================
# Eliminate Small Zones using two passes
#========================================

print('Eliminating small zones (1st pass)...')
arcpy.AddField_management(prelim_zones, 'area_sqm', 'FLOAT')
arcpy.CalculateGeometryAttributes_management(prelim_zones, [['area_sqm','AREA']], '', 'SQUARE_METERS')
zones_layer = arcpy.MakeFeatureLayer_management(prelim_zones, 'zones')
query = """"area_sqm" < 5000"""
arcpy.SelectLayerByAttribute_management(zones_layer, "NEW_SELECTION", query)
zones_eliminated = arcpy.Eliminate_management(zones_layer, os.path.join(temp_dir, 'zones_eliminated_again.shp'), 'LENGTH')

print('Eliminating small zones (2nd pass)...')
arcpy.CalculateGeometryAttributes_management(zones_eliminated, [['area_sqm','AREA']], '', 'SQUARE_METERS')
zones_layer2 = arcpy.MakeFeatureLayer_management(zones_eliminated, 'zones')
query = """"area_sqm" < 10000"""
arcpy.SelectLayerByAttribute_management(zones_layer2, "NEW_SELECTION", query)
zones_eliminated2 = arcpy.Eliminate_management(zones_layer2, os.path.join(temp_dir, 'zones_eliminated_again2.shp'), 'LENGTH')

#==========================
# Eliminate Zone Rings 
#==========================  

print("Eliminating zone inner rings ...")

# Add parts and rings fields
arcpy.AddField_management(zones_eliminated2, 'parts', 'LONG')
arcpy.AddField_management(zones_eliminated2, 'rings', 'LONG')

# Use cursor to populate parts and rings
fields = ["FID", "shape@", "parts", "rings"]
with arcpy.da.UpdateCursor(zones_eliminated2, fields) as cursor:
    for row in cursor:
        shape = row[1]
        parts = shape.partCount
        rings = shape.boundary().partCount
        
        row[2] = parts
        row[3] = rings
        
        cursor.updateRow(row)

# Eliminate polygon part
microzones_no_rings = arcpy.EliminatePolygonPart_management(zones_eliminated2, os.path.join(temp_dir, 'microzones_no_rings.shp'), 'PERCENT',"", 50)

# Get filled zones
filled_zones = arcpy.MakeFeatureLayer_management(microzones_no_rings, 'zones')
query = """"rings" > 1"""
arcpy.SelectLayerByAttribute_management(filled_zones, "NEW_SELECTION", query)

# Erase zones with rings
microzones_rings_erased = arcpy.Erase_analysis(zones_eliminated2, filled_zones, os.path.join(temp_dir, 'zones_erased.shp'))

# add missing zones back
merged_zones = arcpy.Merge_management([microzones_rings_erased, filled_zones], os.path.join(temp_dir, 'merged_zones.shp'))


#==========================
# Finishing touches
#========================== 

print("Applying finishing touches...")

# add persistent unique ID field
arcpy.CalculateField_management(merged_zones,"zone_id",'!{}!'.format('FID'))

# perform spatial join to get TAZ ID - may need more robust method for zones that cross multiple Tazs
microzones = arcpy.SpatialJoin_analysis(merged_zones, taz_polygons, os.path.join(temp_dir, 'microzones.shp'),'JOIN_ONE_TO_ONE', '', '', 'HAVE_THEIR_CENTER_IN')

# Delete extra fields
fields = ["Join_Count", 'TARGET_FID', 'Id', 'ORIG_FID', 'OBJECTID', 'rings', 'parts']
for field in fields:
    try:
        arcpy.DeleteField_management(microzones, field)
    except:
        print('Unable to delete field: {}'.format(field))

# Delete intermediate files (optional)
if delete_intermediate_layers == True:
    trash = [filled_zones, merged_roads, merged_zones, microzones_no_rings, microzones_rings_erased, prelim_zones, roads_clipped, taz_dissolved, taz_outline, zones_eliminated, zones_eliminated2]
    print("Deleting intermediate files...")
    for dataset in trash:
        try:
            arcpy.Delete_management(dataset)
        except:
            print('A file was unable to be deleted')


print('DONE!')