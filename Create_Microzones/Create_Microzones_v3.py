# -*- coding: utf-8 -*-
"""
Created on Fri Apr 24 12:22:01 2020

@author: jreynolds

Creates Micro Traffic Analysis Zones (AKA Microzones or MAZs) from Utah roads network.
Also distributes attributes from REMM, TDM, AGRC
Requires data set folder
"""

import arcpy
import os
import glob
import pandas as pd
import geopandas as gpd
arcpy.env.overwriteOutput = True
arcpy.CheckOutExtension("Spatial")

#==========================
# Args
#==========================

#taz_polygons = os.path.join(os.getcwd(), 'Data\TAZ_geometry.shp') 
taz_polygons = "E:\Micromobility\Data\Zones\TAZ_WFRC_UTM12.shp"
roads = r"E:\Micromobility\Data\Multimodal_Network\Roads.shp"
temp_dir = os.path.join(os.getcwd(), 'Output')
delete_intermediate_layers = False

#====================
# FUNCTIONS
#====================

# returns colnames of a pandas dataframe and their index like R does when you call colnames
def colnames(dataframe):
    values = (list(enumerate(list(dataframe.columns.values), 0)))
    for value in values:
        print(value)
        
# Check fields (works with any ArcGIS compatible table)
def checkFields(dataset):
    fields = arcpy.ListFields(dataset)
    for field in fields:
        print("{0} is a type of {1} with a length of {2}"
              .format(field.name, field.type, field.length))

# Check if a column in a datafram is unique
def isUnique(dataframe, column_name):
    boolean = dataframe[column_name].is_unique
    if boolean == True:
        print("Column: {} is unique")
    else:
        print("Column: {} is NOT unique")


# sets the field map aggregation rule for a provided field/fieldmapping
# example merge rules: sum, mean, first, min, join, count, etc...
def modFieldMapping(fieldMappingsObject, field, mergeRule):
    fieldindex = fieldMappingsObject.findFieldMapIndex(field)
    fieldmap = fieldmappings.getFieldMap(fieldindex)
    fieldmap.mergeRule = mergeRule
    fieldMappingsObject.replaceFieldMap(fieldindex, fieldmap)

# add leading zeroes to TAZ values so that they may be properly used to create the COTAZID
def addLeadingZeroesTAZ(integer):
    if integer < 10:
        return "000{}".format(str(integer))
    if integer >= 10 and integer < 100:
        return "00{}".format(str(integer))
    if integer >= 100 and integer < 1000:
        return "0{}".format(str(integer))
    else:
        return integer

#==========================
# Create Preliminary Zones
#========================== 

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
#query = """"area_sqm" < 10000"""
query = """"area_sqm" < 15000"""
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


# add persistent unique ID field
arcpy.CalculateField_management(merged_zones,"zone_id",'!{}!'.format('FID'))

# perform spatial join to get TAZ ID - may need more robust method for zones that cross multiple Tazs
print('getting TAZ ids...')
microzones = arcpy.SpatialJoin_analysis(merged_zones, taz_polygons, os.path.join(temp_dir, 'microzones.shp'),'JOIN_ONE_TO_ONE', '', '', 'HAVE_THEIR_CENTER_IN')

# Delete extra fields
fields = ["Join_Count", 'TARGET_FID', 'Id', 'ORIG_FID', 'OBJECTID', 'rings', 'parts']
for field in fields:
    try:
        arcpy.DeleteField_management(microzones, field)
    except:
        print('Unable to delete field: {}'.format(field))


# Clip microzones using determined (good) tazs
print('clipping out bad TAZ areas...')
taz_layer = arcpy.MakeFeatureLayer_management(taz_polygons, 'tazs')
query = """not "tazid" in(688, 689,1339, 1340, 2870, 2871, 2872, 1789, 1913, 1914, 1915, 1916, 2854)"""
arcpy.SelectLayerByAttribute_management(taz_layer, "NEW_SELECTION", query)
maz_clipped = arcpy.Clip_analysis(microzones, taz_layer, os.path.join(temp_dir, "maz_clipped.shp"))


# Delete intermediate files (optional)
if delete_intermediate_layers == True:
    print('doing some clean-up...')
    trash = [filled_zones, merged_roads, merged_zones, microzones_no_rings, microzones_rings_erased, prelim_zones, roads_clipped, taz_dissolved, taz_outline, zones_eliminated, zones_eliminated2]
    print("Deleting intermediate files...")
    for dataset in trash:
        try:
            arcpy.Delete_management(dataset)
        except:
            print('A file was unable to be deleted')


#============================================
#============================================
# Attribution
#============================================
#============================================


#================================
# Aggregate REMM Buildings data
#================================ 

"""
from buildings:
    residential_units
    households
    population
    jobs1 (accomodation, food services)
    jobs3 (construction)
    jobs4 (government/education)
    jobs5 (manufacturing)
    jobs6 (office)
    jobs7 (other)
    jobs9 (retail trade)
    jobs10 (wholesale, transport)
    
from taz se

"""

remm_buildings = r"E:\Micromobility\Data\Tables\run1244year2019allbuildings.csv"
remm_parcels = r"E:\Micromobility\Data\Zones\REMM_parcels_UTM12.shp"
microzones_geom =  os.path.join(temp_dir, "maz_clipped.shp")

# load csvs as pandas dataframes
buildings = pd.read_csv(remm_buildings)

# filter columns
buildings_filtered = buildings[['parcel_id', 'parcel_acres','residential_units', 'households', 'population', 'jobs1', 'jobs3', 'jobs4', 'jobs5', 'jobs6', 'jobs7', 'jobs9', 'jobs10']].copy()

# aggregate buildings by parcel id and sum the other columns
buildings_grouped = buildings_filtered.groupby('parcel_id', as_index=False).sum()

# export to csv
# buildings_grouped.to_csv(os.path.join(temp, "buildings_sum_parcelID.csv"), index=False)

# read in parcel features
parcels = gpd.read_file(remm_parcels)
parcels = parcels[['parcel_id', 'geometry']]

#  join to aggregated buildings
parcels_join = parcels.merge(buildings_grouped, left_on = 'parcel_id', right_on = 'parcel_id' , how = 'inner')

# export to shape
parcels_join.to_file(os.path.join(temp_dir, "parcels_with_aggd_buildings_data.shp"))

# convert parcels to points centroids
print('converting parcels to points...')
arcpy.FeatureToPoint_management(os.path.join(temp_dir, "parcels_with_aggd_buildings_data.shp"), os.path.join(temp_dir, "pts_with_aggd_buildings_data.shp"), "INSIDE")

# spatial join here
target_features = os.path.join(temp_dir, "maz_clipped.shp")
join_features = os.path.join(temp_dir, "pts_with_aggd_buildings_data.shp")
output_features = os.path.join(temp_dir, "maz_parcels_spatial_join.shp")

fieldmappings = arcpy.FieldMappings()
fieldmappings.addTable(target_features)
fieldmappings.addTable(join_features)

# Set field aggregation rule using loop
fields_list = ['residentia', 'households', 'population', 'jobs1', 'jobs3', 'jobs4', 'jobs5', 'jobs6', 'jobs7', 'jobs9', 'jobs10']

for field in fields_list:
    modFieldMapping(fieldmappings, field, 'Sum')

# run spatial join
print('joining parcel data to microzones...')
arcpy.SpatialJoin_analysis(target_features, join_features, output_features, "JOIN_ONE_TO_ONE", "KEEP_ALL", fieldmappings, "CONTAINS")

# Select fields
maz_remm_data = gpd.read_file(output_features)
maz_remm_data = maz_remm_data[['zone_id', 'CO_TAZID', 'TAZID', 'CO_FIPS', 'CO_NAME', 'residentia', 'households', 'population', 'jobs1', 'jobs3', 'jobs4', 'jobs5', 'jobs6', 'jobs7', 'jobs9', 'jobs10', 'geometry']]

# export to shape
maz_output = os.path.join(temp_dir, "microzones_with_remm_data.shp")
maz_remm_data.to_file(maz_output)

#==================================
# Disaggregate TAZ level SE data
#================================== 

"""
Age Groups:
AG1) Children - 0 to 17
AG2) Adults - 18 to 64
AG3) Seniors - 65 +

Life Cycles:
LC1) households with no children and seniors
LC2) households with children and no seniors
LC3) households with seniors and may have children

"""

print('creating TAZ level Socioeconomic data layer...')

# Read in taz level se data
taz_se_data = r"E:\Micromobility\Data\Tables\taz_se831_2015.csv"
taz_se_data = pd.read_csv(taz_se_data)
taz_se_data['CO_TAZID'] = taz_se_data['CO_TAZID'].astype(str)

# # Read in taz level life cycle/age data and recreate COTAZID field
taz_se_data2 = r"E:\Micromobility\Data\Tables\LifeCycle_Households_Population_2015_831.csv"
taz_se_data2 = pd.read_csv(taz_se_data2)
taz_se_data2['TAZID'] = taz_se_data2['Z'].map(addLeadingZeroesTAZ) 
taz_se_data2['CO_TAZID'] = taz_se_data2['CO_FIPS'].astype(str) + taz_se_data2['TAZID'].astype(str)

# read in taz polygons
taz_geometry = gpd.read_file(taz_polygons)
taz_geometry['CO_TAZID'] = taz_geometry['CO_TAZID'].astype(str)

# join se data to taz polygons 
taz_join = taz_geometry.merge(taz_se_data, how = 'inner', left_on = 'CO_TAZID', right_on = 'CO_TAZID')
taz_join2= taz_join.merge(taz_se_data2, left_on = 'CO_TAZID', right_on = 'CO_TAZID' , how = 'inner')

# filter to desired columns
taz_join_filt = taz_join2[['CO_TAZID', 'TAZID_x' , 'geometry', 'AVGINCOME','ENROL_ELEM', 'ENROL_MIDL','ENROL_HIGH', 'POP_LC1', 'POP_LC2', 'POP_LC3', 'HHSIZE_LC1', 'HHSIZE_LC2', 'HHSIZE_LC3', 'PCT_POPLC1', 'PCT_POPLC2', 'PCT_POPLC3', 'PCT_AG1', 'PCT_AG2', 'PCT_AG3']]

# export taz data to shape
out_taz_data = os.path.join(temp_dir, "taz_with_se_data.shp")
taz_join_filt.to_file(out_taz_data)

# Distribute attributes larger TAZ attributes to MAZ, using rasters and zonal stats
taz_fields = ['AVGINCOME','ENROL_ELEM', 'ENROL_MIDL','ENROL_HIGH', 'HHSIZE_LC1', 'HHSIZE_LC2', 'HHSIZE_LC3', 'PCT_POPLC1', 'PCT_POPLC2', 'PCT_POPLC3', 'PCT_AG1', 'PCT_AG2', 'PCT_AG3']

for field in taz_fields:
    
    print("Disaggregating {} to maz level...".format(field))
    
    # convert taz se data to raster resolution 20 sq meters 
    out_p2r = os.path.join(temp_dir,"taz_{}.tif".format(field))
    arcpy.FeatureToRaster_conversion(out_taz_data, field, out_p2r, cell_size=20)
 
    # use zonal statistics as table - mean to get table of values for each microzone
    out_table = os.path.join(temp_dir,"taz_{}.dbf".format(field))
    arcpy.sa.ZonalStatisticsAsTable(maz_output, 'zone_id', out_p2r, out_table, 'DATA', 'MEAN')
    out_table_csv = os.path.join(temp_dir,"taz_{}.csv".format(field))
    arcpy.TableToTable_conversion(out_table, os.path.dirname(out_table_csv), os.path.basename(out_table_csv))

    # merge table back with Microzones        
    zonal_table = pd.read_csv(out_table_csv)
    zonal_table =  zonal_table[['zone_id', 'MEAN']]
    zonal_table.columns = ['zone_id', field]
    zonal_table['zone_id'] = zonal_table['zone_id'].astype(str)
    maz_remm_data = maz_remm_data.merge(zonal_table, left_on = 'zone_id', right_on = 'zone_id' , how = 'inner')
    

# normalize school enrollment data
maz_remm_data['ENROL_ELEM'] = maz_remm_data['ENROL_ELEM']/maz_remm_data['population']
maz_remm_data['ENROL_MIDL'] = maz_remm_data['ENROL_MIDL']/maz_remm_data['population']
maz_remm_data['ENROL_HIGH'] = maz_remm_data['ENROL_HIGH']/maz_remm_data['population']


#===================
# Other datasets
#===================

# Transit stops
commuter_rail_stops = r"E:\Micromobility\Data\Attributes\CommuterRailStations_UTA.shp"
light_rail_stops = r"E:\Micromobility\Data\Attributes\LightRailStations_UTA.shp"

# Parks
"""
1:  Acreage > 10
2:  5 < Acreage < 10
3:  Acreage < 5
"""

parks = r"E:\Micromobility\Data\Attributes\ParksLocal.shp"


# Schools
"""
Online/Higher Education (3): NOT ("EDTYPE" = 'Regular Education' AND "GRADEHIGH" = '12' AND "G_Low" > 0)  AND ("SCHOOLTYPE" = 'Online Charter School' OR "SCHOOLTYPE" = 'Online School' OR "SCHOOLTYPE" = 'Regional Campus' OR "SCHOOLTYPE" = 'Residential Campus' )
High Schools(2): "EDTYPE" = 'Regular Education' AND "GRADEHIGH" = '12' AND "G_Low" > 0
Elem/Middle (1): Everything else

"""

schools = r"E:\Micromobility\Data\Attributes\Schools.shp"

# trailheads 
"""
 1) trailhead 0 ) none
"""

trail_heads = r"E:\Micromobility\Data\Attributes\Trailheads.shp"





# manually joined data will have to re-do
final_data = r"E:\Scratch\maz_se_parks_th_sch_lr_cr.shp"

final_data = gpd.read_file(final_data)
final_data2 = final_data[[
 'zone_id',
 'residentia',
 'households',
 'population',
 'jobs1',
 'jobs3',
 'jobs4',
 'jobs5',
 'jobs6',
 'jobs7',
 'jobs9',
 'jobs10',
 'CO_TAZID',
 'TAZID',
 'AVGINCOME',
 'ENROL_ELEM',
 'ENROL_MIDL',
 'ENROL_HIGH',
 'Park_Score',
 'TRAIL_HD',
 'School_CD',
 'LGT_RAIL',
 'COMM_RAIL',
 'geometry']]



final_data2.to_file(os.path.join(temp_dir, "microzones_draft_v2.shp"))



print('DONE!')