import time
import os.path as op
from PyQt4 import QtGui  # , QtCore
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QTAgg
from aston.ui.resources import resfile
from aston.peaks.Integrators import merge_ions
from aston.spectra.Spectrum import Spectrum


class AstonNavBar(NavigationToolbar2QTAgg):
    def __init__(self, canvas, parent=None):
        NavigationToolbar2QTAgg.__init__(self, canvas, parent, False)
        self.parent = parent
        self.ev_time = 0
        self._xypress = []

        #quick function to return icon locs
        icon = lambda l: resfile('aston/ui', 'icons/' + l + '.png')

        #remove the plot adjustment buttons
        self.removeAction(self.actions()[-1])
        self.removeAction(self.actions()[-1])
        self.removeAction(self.actions()[-1])

        #add the alignment tool
        if not hasattr(self, '_actions'):
            self._actions = {}
        self._actions['align'] = QtGui.QAction(QtGui.QIcon(icon('align')), \
          self.parent.tr('Align Chromatogram'), self)
        self._actions['align'].setCheckable(True)
        self.addAction(self._actions['align'])
        self._actions['align'].triggered.connect(self.align)

        self.addSeparator()

        #add the peak tool
        self._actions['peak'] = QtGui.QAction(QtGui.QIcon(icon('peak')), \
          self.parent.tr('Add/Delete Peak'), self)
        self._actions['peak'].setCheckable(True)
        self.addAction(self._actions['peak'])
        self._actions['peak'].triggered.connect(self.peak)

        #add the spectra tool
        self._actions['spectrum'] = QtGui.QAction( \
          QtGui.QIcon(icon('spectrum')), self.parent.tr('Get Spectrum'), self)
        self._actions['spectrum'].setCheckable(True)
        self.addAction(self._actions['spectrum'])
        self._actions['spectrum'].triggered.connect(self.spec)

    def _update_buttons_checked(self):
        #sync button checkstates to match active mode
        self._actions['pan'].setChecked(self._active == 'PAN')
        self._actions['zoom'].setChecked(self._active == 'ZOOM')
        self._actions['peak'].setChecked(self._active == 'PEAK')
        self._actions['spectrum'].setChecked(self._active == 'SPECTRUM')
        self._actions['align'].setChecked(self._active == 'ALIGN')

    def peak(self, *args):
        self._active = 'PEAK'

        self.disconnect_all()
        #if self._active:
        self._idPress = self.canvas.mpl_connect( \
            'button_press_event', self.press_peak)
        self._idRelease = self.canvas.mpl_connect( \
            'button_release_event', self.release_peak)
        self.mode = 'peak'
        self._update_buttons_checked()

        for a in self.canvas.figure.get_axes():
            a.set_navigate_mode(self._active)

        self.set_message(self.mode)

    def press_peak(self, event):
        if event.button != 1 or self.mode != 'peak':
            return
        self._xypress = event.xdata, event.ydata

    def release_peak(self, event):
        if event.button != 1 or self.mode != 'peak':
            return
        if event.xdata is None or event.ydata is None or \
          self._xypress[0] is None or self._xypress[1] is None:
            # if the user clicks just off the plot,
            # the x/y will be None
            return
        dt = self.parent.obj_tab.active_file()
        if dt is None:
            return
        dclicktime = QtGui.QApplication.doubleClickInterval()
        if time.time() - self.ev_time < (dclicktime / 1000.):
            self.ev_time = time.time()
            if abs(self._xypress[0] - event.xdata) > 0.01:
                return
            #TODO: better way to retrieve top ion?
            ion = dt.active_traces(n=0)[0].ions[0]
            #TODO: filter so peak has ion 'ion'
            for pk in dt.children_of_type('peak'):
                if pk.contains(event.xdata, event.ydata, ion=ion):
                    pk.delete()
                    self.parent.plotData(updateBounds=False)
                    break
        else:
            self.ev_time = time.time()
            if abs(self._xypress[0] - event.xdata) < 0.01:
                return

            t0, t1 = event.xdata, self._xypress[0]
            y0, y1 = event.ydata, self._xypress[1]
            if self._xypress[0] < event.xdata:
                t0, t1, y0, y1 = t1, t0, y1, y0

            if event.key == 'shift':
                # if the shift key is down, integrate all of the
                # traces without any baseline offset
                tss = dt.active_traces(twin=(t0, t1))
                pks_found = len(tss) * [[(t0, t1, {'pf': 'manual'})]]
            else:
                tss = dt.active_traces(n=0, twin=(t0, t1))
                pks_found = [[(t0, t1, {'y0': y0, 'y1': y1, 'pf': 'manual'})]]
            pks = self.parent.integrate_peaks(tss, pks_found)
            if event.key == 'shift':
                pks = merge_ions(pks)
            with dt.db:
                dt.children += pks
            dt.info.del_items('s-peaks')
            self.parent.plotData(updateBounds=False)

        self._xypress = []
        self.release(event)

    def align(self, *args):
        self._active = 'ALIGN'

        self.disconnect_all()

        self._idPress = self.canvas.mpl_connect( \
            'button_press_event', self.press_align)
        self._idDrag = self.canvas.mpl_connect( \
            'motion_notify_event', self.drag_align)
        self._idRelease = self.canvas.mpl_connect( \
            'button_release_event', self.release_align)
        self.mode = 'align'
        self._update_buttons_checked()

        for a in self.canvas.figure.get_axes():
            a.set_navigate_mode(self._active)

        self.set_message(self.mode)

    def press_align(self, event):
        dt = self.parent.obj_tab.active_file()
        if dt is None:
            return
        if event.button == 1:
            try:
                x = float(dt.info['t-offset']) - event.xdata
            except:
                x = 0 - event.xdata
            try:
                y = float(dt.info['t-yoffset']) - event.ydata
            except:
                y = 0 - event.ydata
        elif event.button == 3:
            try:
                x = float(dt.info['t-scale']) / event.xdata
            except:
                x = 1 / event.xdata
            try:
                y = float(dt.info['t-yscale']) / event.ydata
            except:
                y = 1 / event.ydata
        self._xypress = x, y

    def drag_align(self, event):
        if self._xypress == []:
            return
        if event.xdata is None or event.ydata is None:
            return
        dt = self.parent.obj_tab.active_file()
        if event.button == 1:
            dt.info['t-offset'] = str(self._xypress[0] + event.xdata)
            dt.info['t-yoffset'] = str(self._xypress[1] + event.ydata)
        elif event.button == 3:
            dt.info['t-scale'] = str(self._xypress[0] * event.xdata)
            dt.info['t-yscale'] = str(self._xypress[1] * event.ydata)
        self.parent.plotData(updateBounds=False)

    def release_align(self, event):
        if self._xypress == []:
            return
        dt = self.parent.obj_tab.active_file()
        dt.save_changes()
        self._xypress = []
        self.release(event)

    def spec(self, *args):
        self._active = 'SPECTRUM'

        self.disconnect_all()
        self._idPress = self.canvas.mpl_connect( \
            'button_press_event', self.press_spectrum)
        self._idRelease = self.canvas.mpl_connect( \
            'button_release_event', self.release_spectrum)
        self.mode = 'spectrum'
        self._update_buttons_checked()

        for a in self.canvas.figure.get_axes():
            a.set_navigate_mode(self._active)

        self.set_message(self.mode)

    def press_spectrum(self, event):
        if event.button != 1 or self.mode != 'spectrum':
            return
        self._xypress = event.xdata, event.ydata

    def release_spectrum(self, event):
        if event.button != 1 or self.mode != 'spectrum':
            return
        #get the specral data of the current point
        dt = self.parent.obj_tab.active_file()
        if dt is None:
            return
        if event.xdata == self._xypress[0]:
            scan = dt.scan(self._xypress[0])
            spec_time = str(self._xypress[0])
        else:
            scan = dt.scan(self._xypress[0], to_time=event.xdata)
            spec_time = str(self._xypress[0]) + '-' + str(event.xdata)

        self.parent.specplotter.set_main_spec(scan, spec_time)
        self.parent.specplotter.plot()

        # draw a line on the main plot for the location
        self.parent.plotter.draw_spec_line(self._xypress[0], \
          event.xdata, linestyle='-')
        if event.key == 'shift':
            info = {'name': str(self._xypress[0])}
            spc = Spectrum(info, scan)
            spc.parent = dt
        self._xypress = []

    def disconnect_all(self):
        if self._idPress is not None:
            self._idPress = self.canvas.mpl_disconnect(self._idPress)
        if self._idDrag is not None:
            self._idDrag = self.canvas.mpl_disconnect(self._idDrag)
        if self._idRelease is not None:
            self._idRelease = self.canvas.mpl_disconnect(self._idRelease)
        self.mode = ''
