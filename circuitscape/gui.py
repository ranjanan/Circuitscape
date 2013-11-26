import os, sys, traceback, logging, time, multiprocessing, tempfile
import numpy as np

import wxversion
try:
    #wxversion.select(['2.9', '2.8', '2.7'])
    wxversion.select('2.8')
except:
    try:
        wxversion.select('2.9')
    except:
        try:
            wxversion.select('2.7')
        except:
            pass

import wx
import wx.lib.newevent
from PythonCard import dialog, model 
from PythonCard.components import button, checkbox, choice, image, staticline, statictext, textfield, spinner, textarea

from compute import Compute, CSIO, __version__
from compute_base import ComputeBase
from cfg import CSConfig
from gui_rsrc import GUI_RSRC

wxLogEvent, EVT_WX_LOG_EVENT = wx.lib.newevent.NewEvent()

class GUILogger(logging.Handler):
    def __init__(self, dest=None):
        logging.Handler.__init__(self)
        self.dest = dest
        self.level = logging.DEBUG
        self.last_gui_yield_time = time.time()

    def flush(self):
        pass

    def emit(self, record):
        try:
            msg = self.format(record)
            msg = msg.strip('\r')
            status_msg = None
            if ('\n' not in msg): # dispay simple info messages in the status bar
                plain_msg = logging._defaultFormatter.format(record)
                if (record.levelname == 'INFO'):
                    status_msg = (plain_msg, 1)
                elif (record.levelname == 'DEBUG'):
                    status_msg = (plain_msg, 2) 
            
            evt = wxLogEvent(message=msg, levelname=record.levelname, status_msg=status_msg)
            wx.PostEvent(self.dest, evt) # @UndefinedVariable
        
            (hours,mins,secs) = ComputeBase.elapsed_time(self.last_gui_yield_time)
            if (secs > 5) or (mins > 0) or (hours > 0):
                self.last_gui_yield_time = time.time()
                wx.SafeYield(None, True)  # @UndefinedVariable
                wx.GetApp().Yield(True)  # @UndefinedVariable
            
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)


class GUI(model.Background):
    OPTIONS_SCENARIO            = ['not entered', 'pairwise', 'one-to-all', 'all-to-one', 'advanced']
    SCENARIO_PAIRWISE_ADVANCED  = [    (0,0),        (1,0),       (1,0),        (1,0),       (0,1)  ]
    
    OPTIONS_HABITAT_MAP_IS_RESISTANCES      = ['not entered', True, False]
    OPTIONS_CONNECT_USING_AVG_RESISTANCES   = ['not entered', True, False]
    OPTIONS_CONNECT_FOUR_NEIGHBORS_ONLY     = ['not entered', True, False]
    OPTIONS_POINT_FILE_CONTAINS_POLYGONS    = ['not entered', False, True]
    OPTIONS_GROUND_FILE_IS_RESISTANCES      = ['not entered', True, False]
    OPTIONS_LOG_LEVEL                       = ['DEBUG', 'INFO', 'WARN', 'ERROR']
    
    COLOR_ENABLED = (0, 0, 160)
    COLOR_DISABLED = (180,180,180)
    
    logger = None
    log_handler = None
    
    def on_initialize(self, event):
        self.state = {}
        self.state['version'] = __version__
        
        #LOAD LAST self.options
        configFile = 'circuitscape.ini'
        self.options = self.LoadOptions(configFile) 
        self.options.version = self.state['version']
        self.options.log_level = 'DEBUG'
        
        ##Set all objects to reflect options
        self.components.Image1.file = get_packaged_resource('cs_logo.jpg')
        self.setWidgets()
        self.components.calcButton.SetFocus()
        self.statusBar = self.CreateStatusBar()
        self.statusBar.SetFieldsCount(3)        
        self.reset_status_bar()
        
        GUI.log_handler = GUILogger(self)
        GUI.logger = ComputeBase._create_logger("circuitscape_gui", getattr(logging, self.options.log_level.upper()), None, False, GUI.log_handler)
        self.Bind(EVT_WX_LOG_EVENT, self.onLogEvent)    

           
    ##MENU ITEMS
    def on_menuFileLoadLast_select(self, event):
        configFile='circuitscape.ini'
        self.options = self.LoadOptions(configFile)
        self.options.version = self.state['version']
        self.reset_status_bar()
        ##Set all objects to reflect options
        self.setWidgets()
        self.components.calcButton.SetFocus()


    def on_menuFileLoadPrev_select(self, event):
        wildcard = "Options Files (*.ini)|*.ini|All Files (*.*)|*.*" 
        result = dialog.fileDialog(self, 'Select Circuitscape Options File', '', '', wildcard ) 
        if result.accepted==True:        
            configFile = result.paths[0]
            self.options = self.LoadOptions(configFile)
            self.options.version = self.state['version']
            self.reset_status_bar()
            #Set all gui objects to reflect options    
            self.setWidgets()
            
            self.components.calcButton.SetFocus()

    def on_menuFileVerifyCode_select(self, event):
        GUI.logger.info('Verifying code (this will take a minute or two)')
        self.statusBar.SetStatusText('Verifying code (this will take a minute or two)',0)
        self.statusBar.SetStatusText('',1)

        outdir = None
        cwd = os.getcwd()
        try:
            root_path = os.path.dirname(__file__)
            outdir = tempfile.mkdtemp()
            if os.path.exists(root_path):
                root_path = os.path.split(root_path)[0]
                os.chdir(root_path)     # otherwise we are running inside a packaged folder and resources are availale at cwd
            from verify import cs_verifyall
            testResult = cs_verifyall(out_path=outdir)
            testsPassed = testResult.wasSuccessful()
        except:
            testsPassed = False
        finally:
            os.chdir(cwd)
            if None != outdir:
                for root, dirs, files in os.walk(outdir, topdown=False):
                    for name in files:
                        os.remove(os.path.join(root, name))
                    for name in dirs:
                        os.rmdir(os.path.join(root, name))
                os.rmdir(outdir)

        if testsPassed:
            dial = wx.MessageDialog(None, 'All tests passed!', 'Verification complete.', wx.OK)  # @UndefinedVariable
            dial.ShowModal()
        else:
            dial = wx.MessageDialog(None, 'Errors were found.  Please see terminal or console for details.', 'Verification failed.', wx.OK)  # @UndefinedVariable
            dial.ShowModal()
        self.reset_status_bar()

    def _get_options_set_in_menu_bar(self):
        self.options.use_unit_currents              = self.menuBar.getChecked('menuOptionsUnitSrcs')
        self.options.use_direct_grounds             = self.menuBar.getChecked('menuOptionsDirectGnds')
        self.options.write_cum_cur_map_only         = self.menuBar.getChecked('menuOptionsCumMap')
        self.options.write_max_cur_maps             = self.menuBar.getChecked('menuOptionsMaxMap')
        self.options.low_memory_mode                = self.menuBar.getChecked('menuOptionsLowMemory')
        self.options.log_transform_maps             = self.menuBar.getChecked('menuOptionsLogCurMap')
        self.options.compress_grids                 = self.menuBar.getChecked('menuOptionsCompressGrids')
        self.options.print_timings                  = self.menuBar.getChecked('menuOptionsPrintTimings')
        self.options.preemptive_memory_release      = self.menuBar.getChecked('menuOptionsPreemptGC')
        self.options.use_mask                       = self.menuBar.getChecked('menuOptionsMask')
        self.options.use_variable_source_strengths  = self.menuBar.getChecked('menuOptionsVarSrc')
        self.options.use_included_pairs             = self.menuBar.getChecked('menuOptionsIncludePairs')
        
        rmvgnd = self.menuBar.getChecked('menuOptionsRmvGnd')
        rmvsrc = self.menuBar.getChecked('menuOptionsRmvSrc')
        if rmvgnd == True:
            if rmvsrc == True:
                self.options.remove_src_or_gnd = 'rmvall'
            else:
                self.options.remove_src_or_gnd = 'rmvgnd'
        elif rmvsrc == True:
            self.options.remove_src_or_gnd = 'rmvsrc'
        else:
            self.options.remove_src_or_gnd = 'keepall'
        
    def on_menuFileSave_select(self, event):
        self.components.habitatFile.SetFocus() #Need to force loseFocus on text boxes to make sure they are updated.
        self.components.outFile.SetFocus()
        self.components.calcButton.SetFocus()
        
        self._get_options_set_in_menu_bar()

        wildcard = '*.ini'
        result = dialog.saveFileDialog(self, 'Choose a file name', '', '', wildcard)
        if result.accepted == True:                
            options_file_name = result.paths[0]
            try:
                self.options.write(options_file_name, True)
            except RuntimeError as ex:
                message = str(ex)
                dial = wx.MessageDialog(None, message, 'Error writing configuration file', wx.OK | wx.ICON_ERROR)  # @UndefinedVariable
                dial.ShowModal()


    def on_menuFileRunBatch_select(self, event):
        wildcard = "Options Files (*.ini)|*.ini" 
        result = dialog.fileDialog(self, 'Select any number of Circuitscape Options Files within one directory', '', '', wildcard ) 
        if result.accepted==True:
            wx.BeginBusyCursor()  # @UndefinedVariable
            GUI.logger.debug('Running Circuitscape in batch mode')
            startTime = time.time()
            startTimeHMS = time.strftime('%H:%M:%S')
            self.statusBar.SetStatusText('Batch start ' + str(startTimeHMS), 0)
            job = 0
            numjobs = len(result.paths)
            for selection in result.paths:
                job += 1
                _configDir, configFile = os.path.split(selection)
                GUI.logger.debug('Processing ' + configFile)
                self.statusBar.SetStatusText('Batch start ' + str(startTimeHMS) + '. Running job ' + str(job) +'/' + str(numjobs), 0)
                
                try:
                    cs = Compute(selection, self)
                except RuntimeError as error:
                    message = str(error)
                    dial = wx.MessageDialog(None, message, 'Error', wx.OK | wx.ICON_ERROR)  # @UndefinedVariable
                    dial.ShowModal()
                    return
                except MemoryError:
                    self.memory_error_feedback()
                    return
                except:
                    self.unknown_exception()
                    return

                try:
                    self.statusBar.SetStatusText('',1)
                    self.statusBar.SetStatusText('',2)
                    result, _solver_failed = cs.compute()
                    GUI.logger.debug('Finished processing ' + configFile)
                except RuntimeError as error:
                    message = str(error)
                    dial = wx.MessageDialog(None, message, 'Error', wx.OK | wx.ICON_ERROR)  # @UndefinedVariable
                    dial.ShowModal()
                except MemoryError:
                    self.memory_error_feedback()
                    return
                except:
                    self.unknown_exception()
                    
            GUI.logger.debug('Done with batch operations.')
            wx.EndBusyCursor()  # @UndefinedVariable
            
            self.components.calcButton.SetFocus()
            self.reset_status_bar()

            (hours,mins,secs) = ComputeBase.elapsed_time(startTime)
            if hours > 0:
                self.statusBar.SetStatusText('Batch job took ' + str(hours) +' hours ' + str(mins) + ' minutes to complete.',2)
            else:
                self.statusBar.SetStatusText('Batch job took ' + str(mins) +' minutes ' + str(secs) + ' seconds to complete.',2)


            
    def on_menuOptionsCumMap_select(self, event):
        self.menuBar.setChecked('menuOptionsCumMap', self.menuBar.getChecked('menuOptionsCumMap'))

    def on_menuOptionsMaxMap_select(self, event):
        self.menuBar.setChecked('menuOptionsMaxMap', self.menuBar.getChecked('menuOptionsMaxMap'))

    def on_menuOptionsLowMemory_select(self, event):
        self.menuBar.setChecked('menuOptionsLowMemory', self.menuBar.getChecked('menuOptionsLowMemory'))

    def on_menuOptionsUnitSrcs_select(self, event):
        self.menuBar.setChecked('menuOptionsUnitSrcs', self.menuBar.getChecked('menuOptionsUnitSrcs'))

    def on_menuOptionsDirectGnds_select(self, event):
        self.menuBar.setChecked('menuOptionsDirectGnds', self.menuBar.getChecked('menuOptionsDirectGnds'))

    def on_menuOptionsLogCurMap_select(self, event):
        self.menuBar.setChecked('menuOptionsLogCurMap', self.menuBar.getChecked('menuOptionsLogCurMap'))

    def on_menuOptionsCompressGrids_select(self, event):
        self.menuBar.setChecked('menuOptionsCompressGrids', self.menuBar.getChecked('menuOptionsCompressGrids'))

    def on_menuOptionsPrintTimings_select(self, event):
        self.menuBar.setChecked('menuOptionsPrintTimings', self.menuBar.getChecked('menuOptionsPrintTimings'))

    def on_menuOptionsPreemptGC_select(self, event):
        self.menuBar.setChecked('menuOptionsPreemptGC', self.menuBar.getChecked('menuOptionsPreemptGC'))

    def on_menuOptionsRmvGnd_select(self, event):
        self.menuBar.setChecked('menuOptionsRmvGnd', self.menuBar.getChecked('menuOptionsRmvGnd'))

    def on_menuOptionsRmvSrc_select(self, event):
        self.menuBar.setChecked('menuOptionsRmvSrc', self.menuBar.getChecked('menuOptionsRmvSrc'))


    def on_menuOptionsMask_select(self, event):
        self.menuBar.setChecked('menuOptionsMask', self.menuBar.getChecked('menuOptionsMask'))
        
        if self.menuBar.getChecked('menuOptionsMask') == True:
            wildcard = "ASCII Raster (*.asc)|*.asc|All Files (*.*)|*.*"
            result = dialog.fileDialog(self, 'Select Raster Mask.  All cells with NODATA or non-positive-integer values will be dropped from habitat map. ', '', '', wildcard) 
            if result.accepted == True: 
                file_name = result.paths[0]
                self.options.mask_file = file_name
            else:
                self.menuBar.setChecked('menuOptionsMask', False)
      

    def on_menuOptionsVarSrc_select(self, event):
        self.menuBar.setChecked('menuOptionsVarSrc', self.menuBar.getChecked('menuOptionsVarSrc'))
        
        if self.menuBar.getChecked('menuOptionsVarSrc') == True:
            wildcard = "Tab-delimited text list (*.txt)|*.txt|All Files (*.*)|*.*" 
            result = dialog.fileDialog(self, 'Select List of Source Strengths', '', '', wildcard ) 
            if result.accepted == True: 
                file_name = result.paths[0]
                self.options.variable_source_file = file_name
            else:
                self.menuBar.setChecked('menuOptionsVarSrc', False)


    def on_menuOptionsIncludePairs_select(self, event):
        self.menuBar.setChecked('menuOptionsIncludePairs', self.menuBar.getChecked('menuOptionsIncludePairs'))
        
        if self.menuBar.getChecked('menuOptionsIncludePairs') == True:
            wildcard = "Tab-delimited text list (*.txt)|*.txt|All Files (*.*)|*.*" 
            result = dialog.fileDialog(self, 'Select Matrix of Focal Node Pairs to Include/Exclude ', '', '', wildcard ) 
            if result.accepted==True: 
                file_name = result.paths[0]
                self.options.included_pairs_file = file_name
            else:
                self.menuBar.setChecked('menuOptionsIncludePairs', False)

    def on_menuFileAbout_select(self, event):
        messagetext = str('Version ' + self.state['version'] + '\n\nhttp://www.circuitscape.org/\n\nBrad McRae and Viral B. Shah\n\nCircuitscape (C) 2008-09. Licensed under LGPL.')
        dial = wx.MessageDialog(None, messagetext, 'Circuitscape', wx.OK)  # @UndefinedVariable
        dial.ShowModal()



    ##CHOICE BOXES
    def on_scenarioChoice_select(self, event):   
        scenario = event.GetSelection()
        self.options.scenario               = GUI.OPTIONS_SCENARIO[scenario]
        pairwise_enabled, advanced_enabled  = GUI.SCENARIO_PAIRWISE_ADVANCED[scenario]
        self.enable_disable_widgets(pairwise_enabled, advanced_enabled)

    def on_habResistanceChoice_select(self, event):   
        hab = event.GetSelection()
        self.options.habitat_map_is_resistances = GUI.OPTIONS_HABITAT_MAP_IS_RESISTANCES[hab]
        

    def on_connCalcChoice_select(self, event):   
        calc = event.GetSelection()
        self.options.connect_using_avg_resistances = GUI.OPTIONS_CONNECT_USING_AVG_RESISTANCES[calc]

    def on_connSchemeChoice_select(self, event):   
        scheme = event.GetSelection()
        self.options.connect_four_neighbors_only = GUI.OPTIONS_CONNECT_FOUR_NEIGHBORS_ONLY[scheme]

    def on_focalNodeChoice_select(self, event):
        choice = event.GetSelection() 
        self.options.point_file_contains_polygons = GUI.OPTIONS_POINT_FILE_CONTAINS_POLYGONS[choice]

    def on_gndResistanceChoice_select(self, event):   
        gnd_resistance = event.GetSelection()
        self.options.ground_file_is_resistances = GUI.OPTIONS_GROUND_FILE_IS_RESISTANCES[gnd_resistance]

    def on_logLevelChoice_select(self, event):
        log_lvl = event.GetSelection()
        self.options.log_level = GUI.OPTIONS_LOG_LEVEL[log_lvl]
        GUI.logger.setLevel(getattr(logging, self.options.log_level.upper()))
        GUI.log_handler.setLevel(getattr(logging, self.options.log_level.upper()))

##CHECK BOXES

    def on_loadPolygonBox_mouseClick(self, event):   
        self.options.use_polygons = event.GetSelection()
        self.components.polygonFile.enabled = self.components.polygonBrowse.enabled = self.options.use_polygons
            
    def on_curMapBox_mouseClick(self, event):   
        self.options.write_cur_maps = event.GetSelection() 
   
    def on_voltMapBox_mouseClick(self, event):   
        self.options.write_volt_maps = event.GetSelection() 

    def on_logRusageBox_mouseClick(self, event):
        self.options.print_rusages = event.GetSelection()
    
##BROWSE BUTTONS
    def on_habitatBrowse_mouseClick(self, event):
        if self.options.data_type == 'network':
            wildcard = "Tab-delimited text list (*.txt)|*.txt|All Files (*.*)|*.*" 
        else:
            wildcard = "ASCII Raster (*.asc)|*.asc|All Files (*.*)|*.*" 
        result = dialog.fileDialog(self, 'Select Raster Habitat Map', '', '', wildcard) 
        if result.accepted == True: 
            file_name = result.paths[0]
            self.components.habitatFile.text = file_name
            self.options.habitat_file = file_name
      
    def on_srcTargetBrowse_mouseClick(self, event):
        wildcard = "Tab-delimited text list (*.txt) or ASCII Raster (*.asc)|*.txt;*.asc|All Files (*.*)|*.*" 
        result = dialog.fileDialog(self, 'Select Source/Target File', '', '', wildcard) 
        if result.accepted == True:        
            file_name = result.paths[0]
            self.components.srcTargetFile.text = file_name                    
            self.options.point_file = file_name

    def on_currentSrcBrowse_mouseClick(self, event):
        wildcard = "Tab-delimited text list (*.txt) or ASCII Raster (*.asc)|*.txt;*.asc|All Files (*.*)|*.*" 
        result = dialog.fileDialog(self, 'Select Source/Target File', '', '', wildcard) 
        if result.accepted == True:        
            file_name = result.paths[0]
            self.components.currentSrcFile.text = file_name                    
            self.options.source_file = file_name

    def on_polygonBrowse_mouseClick(self, event):
        wildcard = "ASCII Raster (*.asc)|*.asc|All Files (*.*)|*.*" 
        result = dialog.fileDialog(self, 'Select Short-Circuit Region Raster', '', '', wildcard) 
        if result.accepted == True:        
            file_name = result.paths[0]
            self.components.polygonFile.text = file_name
            self.options.polygon_file = file_name
        else:
            self.components.polygonFile.text = ''
            
    def on_outBrowse_mouseClick(self, event):
        wildcard = "OUT Files (*.out)|*.out|All Files (*.*)|*.*"
        result = dialog.saveFileDialog(self, 'Choose a Base Output File Name', '', '', wildcard)
        if result.accepted == True:
            file_name = result.paths[0]
            self.components.outFile.text = file_name
            self.options.output_file = file_name

    def on_gndBrowse_mouseClick(self, event):
        wildcard = "Tab-delimited text list (*.txt) or ASCII Raster (*.asc)|*.txt;*.asc|All Files (*.*)|*.*" 
        result = dialog.fileDialog(self, 'Select Ground File', '', '', wildcard ) 
        if result.accepted == True:        
            file_name = result.paths[0]
            self.components.gndFile.text = file_name
            self.options.ground_file = file_name
        
##TEXT BOXES
    def on_habitatFile_loseFocus(self,event):
        self.options.habitat_file = self.components.habitatFile.text        
        
    def on_srcTargetFile_loseFocus(self,event):
        self.options.point_file = self.components.srcTargetFile.text 
            
    def on_currentSrcFile_loseFocus(self,event):
        self.options.source_file = self.components.currentSrcFile.text
        
    def on_polygonFile_loseFocus(self,event):
        self.options.polygon_file = self.components.polygonFile.text
        
    def on_outFile_loseFocus(self,event):
        self.options.output_file = self.components.outFile.text
            
    def on_gndFile_loseFocus(self,event):
        self.options.ground_file = self.components.gndFile.text

    def on_parallelSpin_textUpdate(self, event):
        if self.components.parallelSpin.value > 1:
            self.options.max_parallel = self.components.parallelSpin.value
            self.options.parallelize = True
        else:
            self.options.max_parallel = 1
            self.options.parallelize = False
            
##CALCULATE
    def on_calcButton_mouseClick(self, event):
        self.components.habitatFile.SetFocus() #Need to force loseFocus on text boxes to make sure they are updated.
        self.components.outFile.SetFocus()
        self.components.calcButton.SetFocus()
        
        out_base, _out_ext = os.path.splitext(self.options.output_file)
        if self.options.log_file == None:
            self.options.log_file = out_base + '.log'

        if (self.options.profiler_log_file == None) and (self.options.print_timings or self.options.print_rusages):
            self.options.profiler_log_file = out_base + '_rusages.log'
        
        #Check to see if all inputs are chosen
        (all_options_entered, message) = self.options.check()
        
        if not all_options_entered:
            dial = wx.MessageDialog(None, message, 'Not all options entered', wx.OK | wx.ICON_EXCLAMATION)  # @UndefinedVariable
            dial.ShowModal()
            return
        
        self._get_options_set_in_menu_bar()
                                 
        #save selected options in local directory
        configFile = 'circuitscape.ini'
        self.options.write(configFile)
        try:
            self.options.write(self.options.output_file, True)
        except RuntimeError as ex:
            dial = wx.MessageDialog(None, str(ex), 'Error', wx.OK | wx.ICON_ERROR)  # @UndefinedVariable
            dial.ShowModal()
            return  
                            
        GUI.logger.debug('Calling Circuitscape...')
        startTime = time.strftime('%H:%M:%S')
        self.statusBar.SetStatusText('Job started ' + str(startTime), 0)
        try:
            cs = Compute('circuitscape.ini', GUI.log_handler)
        except RuntimeError as error:
            message = str(error)
            dial = wx.MessageDialog(None, message, 'Error', wx.OK | wx.ICON_ERROR)  # @UndefinedVariable
            dial.ShowModal()
            return
        except:
            self.unknown_exception()
            return

        try:
            terminate = self.checkHeaders()
            if terminate == True:
                return
        except RuntimeError as error:
            message = str(error)
            dial = wx.MessageDialog(None, message, 'Error', wx.OK | wx.ICON_ERROR)  # @UndefinedVariable
            dial.ShowModal()
            return

        if self.options.data_type == 'network':        
            GUI.logger.debug('Running in Network (Graph) Mode')
                            
        if self.options.scenario == 'pairwise':
            try:
                wx.BeginBusyCursor()  # @UndefinedVariable
                self.statusBar.SetStatusText('',1)
                self.statusBar.SetStatusText('',2)                
                resistances, solver_failed = cs.compute()
                wx.EndBusyCursor()  # @UndefinedVariable
                
                self.components.calcButton.SetFocus()

                if solver_failed == True:
                    msg = 'Pairwise resistances (-1 indicates disconnected focal node pair, -777 indicates failed solve):'
                else:
                    msg = 'Pairwise resistances (-1 indicates disconnected node pair):'
                GUI.logger.info(msg + "\n" + np.array_str(resistances, 300))
                GUI.logger.info('Done.')
                
                if solver_failed == True:
                    message = 'At least one solve failed.  Failure is coded as -777 in output resistance matrix.'
                    dial = wx.MessageDialog(None, message, 'Error', wx.OK | wx.ICON_EXCLAMATION)  # @UndefinedVariable
                    dial.ShowModal()
            except MemoryError:
                self.memory_error_feedback()
                return
            except RuntimeError as error:
                message = str(error)
                dial = wx.MessageDialog(None, message, 'Error', wx.OK | wx.ICON_ERROR)  # @UndefinedVariable
                dial.ShowModal()
                return
            except:
                self.unknown_exception()

        elif self.options.scenario == 'advanced':
            try:
                wx.BeginBusyCursor()  # @UndefinedVariable
                self.statusBar.SetStatusText('',1)
                self.statusBar.SetStatusText('',2) 
                _voltages, solver_failed = cs.compute()
                wx.EndBusyCursor()  # @UndefinedVariable
                
                self.components.calcButton.SetFocus()
                
                if solver_failed == True:
                    message = 'Solver failed!'
                    dial = wx.MessageDialog(None, message, 'Error', wx.OK | wx.ICON_EXCLAMATION)  # @UndefinedVariable
                    dial.ShowModal()
                
                GUI.logger.info('Done.')
            except RuntimeError as error:
                message = str(error)
                dial = wx.MessageDialog(None, message, 'Error', wx.OK | wx.ICON_ERROR)  # @UndefinedVariable
                dial.ShowModal()
                return
            except MemoryError:
                self.memory_error_feedback()
                return
            except:
                self.unknown_exception()
                return

        else:
            try:
                wx.BeginBusyCursor()  # @UndefinedVariable
                self.statusBar.SetStatusText('',1)
                self.statusBar.SetStatusText('',2)                                    
                resistances, solver_failed = cs.compute()
                wx.EndBusyCursor()  # @UndefinedVariable
                
                self.components.calcButton.SetFocus()
                
                if self.options.scenario == 'all-to-one':
                    if solver_failed == True:
                        msg = 'Result for each focal node (0 indicates successful calculation, -1 indicates disconnected node, -777 indicates failed solve):'
                    else:
                        msg = 'Result for each focal node (0 indicates successful calculation, -1 indicates disconnected node):'
                elif solver_failed == True:
                    msg = 'Resistances (-1 indicates disconnected node, -777 indicates failed solve):'
                else:
                    msg = 'Resistances (-1 indicates disconnected node):'
                GUI.logger.info(msg + '\n' + np.array_str(resistances, 300))
                GUI.logger.info('Done.')
                
                if solver_failed == True:
                    message = 'At least one solve failed.  Failure is coded as -777 in output node/resistance list.'
                    dial = wx.MessageDialog(None, message, 'Error', wx.OK | wx.ICON_EXCLAMATION)  # @UndefinedVariable
                    dial.ShowModal()
            except RuntimeError as error:
                message = str(error)
                dial = wx.MessageDialog(None, message, 'Error', wx.OK | wx.ICON_ERROR)  # @UndefinedVariable
                dial.ShowModal()
            except MemoryError:
                self.memory_error_feedback()
                return
            except:
                self.unknown_exception()            
            self.reset_status_bar()        


    def checkHeaders(self):
        """Checks to make sure headers (with cell size, number of cols, etc) match for input rasters."""  
        if self.options.data_type == 'network':
            return
        match_files = []
        if self.options.use_polygons == True:
            match_files.append(self.options.polygon_file)
        
        if os.path.splitext(self.options.point_file)[1] == '.asc':
            match_files.append(self.options.point_file)
        
        if self.options.use_mask == True:
            match_files.append(self.options.mask_file)
        
        headers_match = CSIO.match_headers(self.options.habitat_file, match_files)

        if headers_match == False:
            result = wx.MessageDialog(None, "Raster map headers do not match.  Circuitscape can try to resample maps to match the habitat map (Beta code, no guarantees). \n\nNote:all maps MUST be in the same projection.  Some focal nodes or short-circuit regions may be lost. \n\nUsing the 'Export to Circuitscape' ArcGIS tool is a better bet.\n\nContinue?", "Warning", wx.YES_NO).ShowModal()  # @UndefinedVariable
            return (result == wx.ID_NO) # @UndefinedVariable
        return False


##Error handling
    def unknown_exception(self):
        try:
            dial = wx.MessageDialog(None, 'An unknown error occurred.  Please see message in terminal.', 'Error', wx.OK | wx.ICON_ERROR)  # @UndefinedVariable
            dial.ShowModal()
            e_type, value, tb = sys.exc_info()
            info = traceback.extract_tb(tb)
            print 'full traceback:'
            print info
            print '***************'
            filename, lineno, function, _text = info[-1] # last line only
            print "\n %s:%d: %s: %s (in %s)" % (filename, lineno, e_type.__name__, str(value), function)
        finally:
            e_type = value = tb = None # clean up
 
    def memory_error_feedback(self):
        GUI.logger.error('Circuitscape ran out of memory. Please see user guide for information about memory requirements.')
        message='Circuitscape ran out of memory. \nPlease see user guide for information about memory requirements.'
        dial = wx.MessageDialog(None, message, 'Error', wx.OK | wx.ICON_ERROR)  # @UndefinedVariable
        dial.ShowModal()
        try:
            e_type, value, tb = sys.exc_info()
            info = traceback.extract_tb(tb)
            print 'full traceback:'
            print info
            print '***************'
            filename, lineno, function, _text = info[-1] # last line only
            print "\n %s:%d: %s: %s (in %s)" % (filename, lineno, e_type.__name__, str(value), function)
        finally:
            e_type = value = tb = None # clean up

        
###SUBROUTINES
    def setWidgets(self):
        idx = GUI.OPTIONS_SCENARIO.index(self.options.scenario)
        self.components.scenarioChoice.SetSelection(idx)
        pairwise_enabled, advanced_enabled = GUI.SCENARIO_PAIRWISE_ADVANCED[idx]
        self.enable_disable_widgets(pairwise_enabled, advanced_enabled)

        self.components.habitatFile.text = self.options.habitat_file
        self.components.srcTargetFile.text = self.options.point_file
        
        idx = GUI.OPTIONS_POINT_FILE_CONTAINS_POLYGONS.index(self.options.point_file_contains_polygons)
        self.components.focalNodeChoice.SetSelection(idx)
            
        self.components.polygonFile.text = self.options.polygon_file
        self.components.polygonBrowse.enabled = self.components.polygonFile.enabled = (self.options.use_polygons == True)

        self.components.currentSrcFile.text = self.options.source_file
        self.components.gndFile.text = self.options.ground_file
        self.components.outFile.text = self.options.output_file
        
        idx = GUI.OPTIONS_HABITAT_MAP_IS_RESISTANCES.index(self.options.habitat_map_is_resistances)
        self.components.habResistanceChoice.SetSelection(idx)

        idx = GUI.OPTIONS_GROUND_FILE_IS_RESISTANCES.index(self.options.ground_file_is_resistances)
        self.components.gndResistanceChoice.SetSelection(idx)

        idx = GUI.OPTIONS_CONNECT_FOUR_NEIGHBORS_ONLY.index(self.options.connect_four_neighbors_only)
        self.components.connSchemeChoice.SetSelection(idx)
            
        idx = GUI.OPTIONS_CONNECT_USING_AVG_RESISTANCES.index(self.options.connect_using_avg_resistances)
        self.components.connCalcChoice.SetSelection(idx)
        
        idx = GUI.OPTIONS_LOG_LEVEL.index(self.options.log_level)
        self.components.logLevelChoice.SetSelection(idx)
        if GUI.logger != None:
            GUI.logger.setLevel(getattr(logging, self.options.log_level.upper()))

        if GUI.log_handler != None:
            GUI.log_handler.setLevel(getattr(logging, self.options.log_level.upper()))

        self.components.parallelSpin.value = self.components.parallelSpin.max = 1
        if sys.platform.startswith('win'):
            self.options.parallelize = False
        else:
            self.components.parallelSpin.max = n_cpus = multiprocessing.cpu_count()
            
            if self.options.max_parallel == 1:
                self.options.parallelize = False
                
            if self.options.parallelize:
                if self.options.max_parallel == 0:
                    self.options.max_parallel = n_cpus
                else:
                    self.options.max_parallel = min(self.options.max_parallel, n_cpus)
                self.components.parallelSpin.value = self.options.max_parallel
            
        self.components.loadPolygonBox.checked  = self.options.use_polygons
        self.components.curMapBox.checked       = self.options.write_cur_maps
        self.components.voltMapBox.checked      = self.options.write_volt_maps
        self.components.logRusageBox.checked    = self.options.print_rusages

        self.menuBar.setChecked('menuOptionsUnitSrcs',          self.options.use_unit_currents)
        self.menuBar.setChecked('menuOptionsCumMap',            self.options.write_cum_cur_map_only)
        self.menuBar.setChecked('menuOptionsMaxMap',            self.options.write_max_cur_maps)
        self.menuBar.setChecked('menuOptionsLowMemory',         self.options.low_memory_mode)

        self.menuBar.setChecked('menuOptionsLogCurMap',         self.options.log_transform_maps)
        self.menuBar.setChecked('menuOptionsCompressGrids',     self.options.compress_grids)
        self.menuBar.setChecked('menuOptionsPrintTimings',      self.options.print_timings)
        self.menuBar.setChecked('menuOptionsPreemptGC',         self.options.preemptive_memory_release)
        self.menuBar.setChecked('menuOptionsUnitSrcs',          self.options.use_unit_currents)
        self.menuBar.setChecked('menuOptionsDirectGnds',        self.options.use_direct_grounds)
        self.menuBar.setChecked('menuOptionsMask',              self.options.use_mask)
        self.menuBar.setChecked('menuOptionsVarSrc',            self.options.use_variable_source_strengths)
        self.menuBar.setChecked('menuOptionsIncludePairs',      self.options.use_included_pairs)
        
        self.menuBar.setChecked('menuOptionsRmvGnd',            self.options.remove_src_or_gnd in ['rmvall', 'rmvgnd'])
        self.menuBar.setChecked('menuOptionsRmvSrc',            self.options.remove_src_or_gnd in ['rmvall', 'rmvsrc'])
            
        
    def enable_disable_network_widgets(self, networkEnabled):
        if networkEnabled == True:
            setting = False
            self.components.focalNodeChoice.SetSelection(1)            
        else:
            setting = True
        self.components.polygonFile.enabled = setting
        self.components.polygonBrowse.enabled = setting
        self.components.connSchemeChoice.enabled = setting
        self.components.connCalcChoice.enabled = setting
        self.components.loadPolygonBox.enabled = setting                                
        
                
    def enable_disable_widgets(self, pairwiseEnabled, advancedEnabled):
        is_pairwise_scenario = (self.options.scenario == 'pairwise')
        
        self.components.currentSrcFile.enabled      = advancedEnabled
        self.components.currentSrcBrowse.enabled    = advancedEnabled
        self.components.gndFile.enabled             = advancedEnabled
        self.components.gndBrowse.enabled           = advancedEnabled
        
        self.menuBar.setEnabled('menuOptionsUnitSrcs',      advancedEnabled)
        self.menuBar.setEnabled('menuOptionsDirectGnds',    advancedEnabled)  
        self.menuBar.setEnabled('menuOptionsRmvGnd',        advancedEnabled)   
        self.menuBar.setEnabled('menuOptionsRmvSrc',        advancedEnabled)
        
        self.components.gndResistanceChoice.enabled     = advancedEnabled
        self.components.focalNodeChoice.enabled         = pairwiseEnabled
        
        self.components.polygonBrowse.enabled           = True
        self.components.srcTargetFile.enabled           = pairwiseEnabled
        self.components.srcTargetBrowse.enabled         = pairwiseEnabled
        
        self.menuBar.setEnabled('menuOptionsCumMap',        pairwiseEnabled)    
        self.menuBar.setEnabled('menuOptionsMaxMap',        pairwiseEnabled)
        self.menuBar.setEnabled('menuOptionsLowMemory',     pairwiseEnabled and is_pairwise_scenario)
        self.menuBar.setEnabled('menuOptionsIncludePairs',  pairwiseEnabled) 
        self.menuBar.setEnabled('menuOptionsVarSrc',        pairwiseEnabled and not is_pairwise_scenario)

        self.components.parallelSpin.enabled = is_pairwise_scenario

        foreColor = GUI.COLOR_ENABLED if pairwiseEnabled else GUI.COLOR_DISABLED
        self.components.pairwiseOptionsTitle.foregroundColor    = \
            self.components.srcTargetFileText.foregroundColor       = foreColor
        
        foreColor = GUI.COLOR_ENABLED if is_pairwise_scenario else GUI.COLOR_DISABLED
        self.components.parallelizeText.foregroundColor = foreColor
                    
        foreColor = GUI.COLOR_ENABLED if advancedEnabled else GUI.COLOR_DISABLED
        self.components.gndFileText.foregroundColor             = \
            self.components.advancedOptionsTitle.foregroundColor    = \
            self.components.srcFileText.foregroundColor             = foreColor


    def LoadOptions(self, config_file):
        """Sets options based on configuration file from last run or sets default options if no file exists."""
        options = CSConfig()
        try:
            options = CSConfig(config_file)
        except:
            pass
        return options   

    def on_clearLogsButton_mouseClick(self, event):
        self.components.logMessages.clear()
        self.reset_status_bar()

    def onLogEvent(self, event):
        self.components.logMessages.appendText(event.message + '\n')
        if event.status_msg != None:
            self.statusBar.SetStatusText(event.status_msg[0], event.status_msg[1])
            if event.status_msg[1] == 1:
                self.statusBar.SetStatusText('', 2)
        event.Skip()

    def reset_status_bar(self):
        if self.options.data_type == 'network':
            self.enable_disable_network_widgets(True)        
            statustext=str('V ' + self.state['version']+' BETA NETWORK MODE')            
        else:
            statustext=str('Version ' + self.state['version'] + ' Ready.')
            self.enable_disable_network_widgets(False)            
        self.statusBar.SetStatusText(statustext,0)
        self.statusBar.SetStatusText('', 1)
        self.statusBar.SetStatusText('', 2)

def get_packaged_resource(filename):
    res_path = os.path.join(os.path.dirname(__file__), filename)
    if not os.path.exists(res_path):
        res_path = filename     # we are running inside packaged app. resources packaged separately, accessible at cwd
    return res_path
    
def show_gui():
    app = model.Application(GUI, rsrc=GUI_RSRC)
    app.MainLoop()
                
if __name__ == '__main__':
    show_gui()
