# -*- coding: utf-8 -*-
"""
Created on Tue Apr 21 07:32:39 2020

@author: jreynolds bgranberg
"""

import arcpy
import os
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

# Args
taz_polygons = r'E:\Data\TAZ_geometry.shp'
roads = r'E:\Data\Roads.shp'
temp_dir = r'E:\Projects\Misc\Create_Microzones\Output'

#==========================
# Create Preliminary Zones
#========================== 

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
print("Creating preliminary zones...")
prelim_zones = arcpy.FeatureToPolygon_management(merged_roads, os.path.join(temp_dir,"prelim_zones.shp"))

#==========================
# Eliminate Inner Rings
#========================== 

# Add parts and rings fields
arcpy.AddField_management(prelim_zones, 'parts', 'LONG')
arcpy.AddField_management(prelim_zones, 'rings', 'LONG')

# Use cursor to populate parts and rings
print("Getting parts and rings...")
fields = ["FID", "shape@", "parts", "rings"]
with arcpy.da.UpdateCursor(prelim_zones, fields) as cursor:
    for row in cursor:
        shape = row[1]
        parts = shape.partCount
        rings = shape.boundary().partCount
        
        row[2] = parts
        row[3] = rings
        
        cursor.updateRow(row)

# Eliminate polygon part
print("Removing zone inner rings...")
zones_eliminated = arcpy.EliminatePolygonPart_management(prelim_zones, os.path.join(temp_dir, 'zones_eliminated.shp'), 'PERCENT',"", 50)

# Get filled zones
zones_layer = arcpy.MakeFeatureLayer_management(zones_eliminated, 'zones')
query = """"rings" > 1"""
arcpy.SelectLayerByAttribute_management(zones_layer, "NEW_SELECTION", query)

# Erase zones with rings
zones_erased = arcpy.Erase_analysis(prelim_zones, zones_layer, os.path.join(temp_dir, 'zones_erased.shp'))

# add missing zones back
merged_zones = arcpy.Merge_management([zones_erased, zones_layer], os.path.join(temp_dir, 'merged_zones.shp'))

#==========================
# Other Stuff
#========================== 

# add persistent unique ID field
arcpy.CalculateField_management(merged_zones,"zone_id",'!{}!'.format('FID'))

# perform spatial join to get TAZ ID - may need more robust method for zones that cross multiple Tazs
print("Getting TAZ IDs...")
microzones = arcpy.SpatialJoin_analysis(merged_zones, taz_polygons, os.path.join(temp_dir, 'microzones.shp'),'JOIN_ONE_TO_ONE', '', '', 'HAVE_THEIR_CENTER_IN')

# Delete extra fields
print("Deleting extra fields...")
fields = ["Join_Count", 'TARGET_FID', 'Id', 'ORIG_FID', 'OBJECT_ID']
for field in fields:
    try:
        arcpy.DeleteField_management(microzones, field)
    except:
        print('Unable to delete field: {}'.format(field))


#==========================
# Eliminate Small Polygons
#==========================       

# Calc Area
arcpy.AddField_management(microzones, 'area_sqkm', 'FLOAT')
arcpy.CalculateGeometryAttributes_management(microzones, [['area_sqkm','AREA']], '', 'SQUARE_KILOMETERS')

microzones_layer = arcpy.MakeFeatureLayer_management(microzones, 'zones')
query = """"area_sqkm" < .005"""
arcpy.SelectLayerByAttribute_management(microzones_layer, "NEW_SELECTION", query)

print('Eliminating parts again...')
microzones_eliminated = arcpy.Eliminate_management(microzones_layer, os.path.join(temp_dir, 'zones_eliminated_again.shp'), 'LENGTH')

microzones_eliminated_layer = arcpy.MakeFeatureLayer_management(microzones_eliminated, 'zones')
query = """"area_sqkm" < .010"""
arcpy.SelectLayerByAttribute_management(microzones_eliminated_layer, "NEW_SELECTION", query)

print('Eliminating parts again...')
microzones_eliminated2 = arcpy.Eliminate_management(microzones_eliminated_layer, os.path.join(temp_dir, 'zones_eliminated_again2.shp'), 'LENGTH')

#==========================
# Eliminate Rings Again
#==========================  

# Use cursor to populate parts and rings
print("Getting parts and rings (2)...")
fields = ["FID", "shape@", "parts", "rings"]
with arcpy.da.UpdateCursor(microzones_eliminated2, fields) as cursor:
    for row in cursor:
        shape = row[1]
        parts = shape.partCount
        rings = shape.boundary().partCount
        
        row[2] = parts
        row[3] = rings
        
        cursor.updateRow(row)

# Eliminate polygon part
print("Removing zone inner rings (2)...")
microzones_no_rings = arcpy.EliminatePolygonPart_management(microzones_eliminated2, os.path.join(temp_dir, 'microzones_carmelo.shp'), 'PERCENT',"", 50)

# Get filled zones
microzones_no_rings_layer = arcpy.MakeFeatureLayer_management(microzones_no_rings, 'zones')
query = """"rings" > 1"""
arcpy.SelectLayerByAttribute_management(microzones_no_rings_layer, "NEW_SELECTION", query)

# Erase zones with rings
microzones_erased = arcpy.Erase_analysis(microzones_eliminated2, microzones_no_rings_layer, os.path.join(temp_dir, 'zones_erased.shp'))

# add missing zones back
merged_zones = arcpy.Merge_management([microzones_erased, microzones_no_rings_layer], os.path.join(temp_dir, 'microzones2.shp'))



print('DONE!')