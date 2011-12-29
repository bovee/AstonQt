from PyQt4 import QtCore, QtGui

class FileTreeModel(QtCore.QAbstractItemModel):
    def __init__(self, database=None, treeView=None, masterWindow=None, *args): 
        from aston.Database import AstonDatabase
        import os.path as op
        QtCore.QAbstractItemModel.__init__(self, *args) 
        
        self.database = AstonDatabase(op.join(database,'aston.sqlite'))
        self.projects = self.database.getProjects()
        self.fields = ['Name','Vis?','Traces','File Name']
        self.masterWindow = masterWindow

        if treeView is not None:
            self.treeView = treeView
            
            #set up proxy model
            self.proxyMod = FilterModel() #QtGui.QSortFilterProxyModel()
            self.proxyMod.setSourceModel(self)
            self.proxyMod.setDynamicSortFilter(True)
            self.proxyMod.setFilterKeyColumn(0)
            self.proxyMod.setFilterCaseSensitivity(False)
            treeView.setModel(self.proxyMod)
            treeView.setSortingEnabled(True)
            
            #set up selections
            treeView.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
            treeView.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
            treeView.clicked.connect(self.itemSelected)
            
            #set up right-clicking
            treeView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            treeView.customContextMenuRequested.connect(self.rightClickMenu)
            treeView.header().setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            treeView.header().customContextMenuRequested.connect(self.rightClickMenuHead)
            
            #set up drag and drop
            treeView.setDragEnabled(True)
            treeView.setAcceptDrops(True)
            treeView.setDragDropMode(QtGui.QAbstractItemView.DragDrop)
            treeView.dragMoveEvent = self.dragMoveEvent

            #prettify
            treeView.expandAll()
            treeView.resizeColumnToContents(0)
            treeView.resizeColumnToContents(1)

    def dragMoveEvent(self,event):
        index = self.proxyMod.mapToSource(self.treeView.indexAt(event.pos()))
        if not index.parent().isValid() and \
           event.mimeData().hasFormat('application/x-aston-file'):
            QtGui.QTreeView.dragMoveEvent(self.treeView,event)
        else:
            event.ignore()

    def mimeTypes(self):
        types = QtCore.QStringList()
        types.append('text/plain')
        types.append('application/x-aston-file')
        return types

    def mimeData(self,indexList):
        fname_lst = []
        fid_lst = []
        for i in indexList:
            if i.column() == 0:
                fname_lst.append(i.internalPointer().filename)
                fid_lst.append(':'.join([str(j) for j in i.internalPointer().fid]))
        data = QtCore.QMimeData()
        data.setText('\n'.join(fname_lst))
        data.setData('application/x-aston-file',','.join(fid_lst))
        return data

    def dropMimeData(self,data,action,row,col,parent):
        #TODO: drop files into library?
        fids = data.data('application/x-aston-file')
        if not parent.isValid(): return False
        self.beginResetModel()
        for pid,fid in [i.split(':') for i in fids.split(',')]:
            if pid == 'None': fles = self.database.getProjFiles(None)
            else: fles = self.database.getProjFiles(int(pid))
            for dt in fles:
                if dt.fid[1] == int(fid):
                    dt.fid = (parent.internalPointer()[0],int(fid))
                    self.database.updateFile(dt)
                    break
        self.endResetModel()
        return True
        
    def supportedDropActions(self):
        return QtCore.Qt.MoveAction

    def index(self,row,column,parent):
        if not parent.isValid():
            projid = self.projects[row]
            return self.createIndex(row,column,projid)
        else:
            projid = parent.internalPointer()[0]
            datafile = self.database.getProjFiles(projid)[row]
            return self.createIndex(row,column,datafile)

    def parent(self,index):
        if not index.isValid():
            return QtCore.QModelIndex()
        elif type(index.internalPointer()) is list or index.internalPointer() is None:
            return QtCore.QModelIndex()
        else:
            projid = index.internalPointer().fid[0]
            row = [i[0] for i in self.projects].index(projid)
            #figure out the project row and projid of the given fileid
            return self.createIndex(row,0,self.projects[row])

    def rowCount(self,parent):
        if not parent.isValid():
            #top level: return number of projects
            return len(self.projects)
        elif type(parent.internalPointer()) is list:
            #return number of files in a given project
            projid = parent.internalPointer()[0]
            return len(self.database.getProjFiles(projid))
        else:
            return 0

    def columnCount(self,parent):
        return len(self.fields)

    def data(self,index,role):
        rslt = None

        fld = self.fields[index.column()].lower()
        if not index.parent().isValid():
            #return info about a project
            if fld == 'name' and role == QtCore.Qt.DisplayRole:
                rslt = self.projects[index.row()][1]
        else:
            #return info about a file
            f = index.internalPointer()
            if fld == 'vis?' and role == QtCore.Qt.CheckStateRole:
                if f.visible: rslt = QtCore.Qt.Checked
                else: rslt = QtCore.Qt.Unchecked
            elif role == QtCore.Qt.DisplayRole or role == QtCore.Qt.EditRole:
                if fld == 'name' : rslt = f.name
                elif fld == 'file name': rslt = f.shortFilename()
                elif fld == 'scans': rslt = str(len(f.time()))
                elif fld == 'start time': rslt = str(min(f.time()))
                elif fld == 'end time': rslt = str(max(f.time()))
                elif fld in f.info.keys(): rslt = f.info[fld]
        return rslt

    def headerData(self,col,orientation,role):
        rslt = None
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            rslt = self.fields[col]
        return rslt

    def setData(self, index, data, role):
        data = str(data)
        col = self.fields[index.column()].lower()
        if not index.parent().isValid():
            if col == 'name':
                proj_id = index.internalPointer()[0]
                self.database.addProject(data,proj_id)
                self.projects[index.row()][1] = data
        else:
            if col == 'vis?':
                index.internalPointer().visible = data == '2'
                #redraw the main plot
                self.masterWindow.plotData()
            elif col in ['traces','scale','offset','smooth',
              'smooth order','smooth window','remove periodic noise']:
                index.internalPointer().info[col] = data
                if index.internalPointer().visible:
                    self.masterWindow.plotData()
            elif col == 'name':
                index.internalPointer().name = data
            else:
                index.internalPointer().info[col] = data
            index.internalPointer().saveChanges()
        self.dataChanged.emit(index,index)
        return True
        
    def flags(self, index):
        col = self.fields[index.column()].lower()
        dflags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        if not index.isValid():
            return dflags
        if not index.parent().isValid():
            if index.internalPointer()[0] is not None and col == 'name':
                return  dflags | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsDropEnabled
            else:
                return dflags | QtCore.Qt.ItemIsDropEnabled
        else:
            dflags = dflags | QtCore.Qt.ItemIsDragEnabled
            if col == 'vis?':
                return dflags | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsUserCheckable
            elif col in ['file name']:
                return dflags
            else:
                return dflags | QtCore.Qt.ItemIsEditable

    def itemSelected(self):
        #TODO: update an info window?
        from .PeakTable import PeakTreeModel
        #redraw the spectral line as gray
        self.masterWindow.plotter.drawSpecLine(self.masterWindow.specplotter.specTime,linestyle='--')

        #remove all of the peak patches from the main plot
        if self.masterWindow.ptab_mod is not None:
            self.masterWindow.ptab_mod.clearPatches()
        #recreate the table of peaks for the new files
        #if any([i.visible for i in self.returnSelFiles()]):
        self.masterWindow.ptab_mod = PeakTreeModel(self.database, self.masterWindow.ui.peakTreeView, self.masterWindow, self.masterWindow.ftab_mod.returnSelFiles())
        #else:
        #    self.masterWindow.ptab_mod = PeakTreeModel(self.database, self.masterWindow.ui.peakTreeView, self.masterWindow)

    def rightClickMenu(self,point):
        index = self.proxyMod.mapToSource(self.treeView.indexAt(point))
        menu = QtGui.QMenu(self.treeView)

        if index.isValid():
            if not index.parent().isValid():
                menu.addAction('New Project',self.addProject)
                if index.internalPointer()[0] is not None:
                    delAc = menu.addAction('Delete Project',self.delProject)
                    delAc.setData(index.internalPointer()[0])
            else:
                pass
        else:
            menu.addAction('New Project',self.addProject)

        if not menu.isEmpty():
            menu.exec_(self.treeView.mapToGlobal(point))

    def rightClickMenuHead(self,point):
        menu = QtGui.QMenu(self.treeView)
        pos_flds = ['Vis?','Traces','File Name','Date','Operator', \
                    'Method','Type','Scans','Start Time','End Time', \
                    'Vial Position','Sequence Number','Units']
        for fld in pos_flds:
            ac = menu.addAction(fld,self.rightClickMenuHeadHandler)
            ac.setCheckable(True)
            if fld in self.fields: ac.setChecked(True)
        if not menu.isEmpty(): menu.exec_(self.treeView.mapToGlobal(point))
    
    def rightClickMenuHeadHandler(self):
        fld = str(self.sender().text())
        if fld == 'Name': return
        self.beginResetModel()
        if fld in self.fields:
            self.fields.remove(fld)
        else:
            self.treeView.resizeColumnToContents(len(self.fields)-1)
            self.fields.append(fld)
        self.endResetModel()

    def addProject(self):
        self.beginResetModel()
        self.database.addProject('New Project')
        self.projects = self.database.getProjects()
        self.endResetModel()

    def delProject(self):
        #TODO: move files back to 'Unsorted' project
        proj_id = self.sender().data()
        self.beginResetModel()
        self.database.delProject(proj_id)
        self.projects = self.database.getProjects()
        self.endResetModel()

    #The following methods are not being overridden, but are here
    #because they rely upon data only know to the file table.

    def returnChkFiles(self):
        #TODO: this should return the checked files in order
        #returns the files checked as visible in the file list
        #return [i for i in self.database.files if i.visible]
        chkFiles = []
        for i in range(self.proxyMod.rowCount(QtCore.QModelIndex())):
            prjNode = self.proxyMod.index(i,0,QtCore.QModelIndex())
            for j in range(self.proxyMod.rowCount(prjNode)):
                f = self.proxyMod.mapToSource(self.proxyMod.index(j,0,prjNode)).internalPointer()
                if f.visible:
                    chkFiles.append(f)
        return chkFiles

    def returnSelFile(self):
        #returns the file currently selected in the file list
        #used for determing which spectra to display on right click, etc.
        tab_sel = self.treeView.selectionModel()
        if not tab_sel.currentIndex().isValid: return

        ind = self.proxyMod.mapToSource(tab_sel.currentIndex())
        if ind.internalPointer() is None: return
        return ind.internalPointer()

    def returnSelFiles(self):
        #returns the files currently selected in the file list
        #used for displaying the peak list, etc.
        tab_sel = self.treeView.selectionModel()
        files = []
        for i in tab_sel.selectedRows():
            if i.parent().isValid():
                files.append(i.model().mapToSource(i).internalPointer())
        return files

class FilterModel(QtGui.QSortFilterProxyModel):
    def __init__(self,parent=None):
        super(FilterModel,self).__init__(parent)

    def filterAcceptsRow(self,row,index):
        if not index.isValid(): return True
        else: return super(FilterModel,self).filterAcceptsRow(row,index)

