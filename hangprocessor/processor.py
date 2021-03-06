import os
import json
import subprocess
import time
from report import generateReport
import traceback

class Processor(object):
    def __init__(self, config):
        self.config = config

    def processsingle(self, dumpfile):
        outfile = dumpfile + '.processed'
        errfile = dumpfile + '.processingerror'

        outfd = open(outfile, 'wb')
        errfd = open(errfile, 'wb')

        command = [self.config.minidump_stackwalk_path, '-m', dumpfile] + self.config.symbol_paths
        p = subprocess.Popen(command, stdout=outfd, stderr=errfd)
        outfd.close()

        def waitfunc():
            r = p.wait()
            if r == 0:
                errfd.close()
                os.unlink(errfile)
            else:
                errfd.seek(0, os.SEEK_END)
                print >>errfd, "\n[minidump-stackwalk failed with code %i]" % r
                errfd.close()
                os.unlink(outfile)

        return waitfunc

    def process(self, dumpdir):
        print "[%s] Processing %s" % (time.asctime(), dumpdir)

        extrafd = open(os.path.join(dumpdir, 'extra.json'))
        extra = json.load(extrafd)
        extrafd.close()

        dumps = ['plugin']
        if 'additional_minidumps' in extra:
            dumps.extend(extra['additional_minidumps'].split(','))

        waitfuncs = [self.processsingle(os.path.join(dumpdir, 'minidump_%s.dmp' % dump)) for dump in dumps]
        for f in waitfuncs:
            f()

        reportFile = os.path.join(dumpdir, 'report.html')
        fd = open(reportFile, 'w')
        fd.write(generateReport(dumpdir))
        fd.close()

        if self.config.reporting_server and self.config.reporting_directory:
            uuid = os.path.basename(dumpdir)
            year = uuid[3:7]
            month = uuid[7:9]
            day = uuid[9:11]
            remoteDir = os.path.join(self.config.reporting_directory, year, '%s-%s' % (month, day))
            remoteFile = os.path.join(remoteDir, uuid + '.html')

            fd = open(reportFile)
            subprocess.check_call(['ssh', self.config.reporting_server, 'mkdir', '-p', remoteDir, '&&', 'cat', '>', remoteFile], stdin=fd)
            fd.close()

    def searchandprocess(self):
        print "[%s] Searching for new records to process" % (time.asctime())
        for name in os.listdir(self.config.processor_queue_path):
            linkpath = os.path.join(self.config.processor_queue_path, name)
            try:
                dumpdir = os.readlink(linkpath)
            except OSError:
                print "[%s] Found record '%s' which is not a symlink. Deleting." % (time.asctime(), name)
                os.unlink(linkpath)
                continue

            if not os.path.isabs(dumpdir):
                print "[%s] Found record '%s' which points to non-absolute path '%s'. Deleting." % (time.asctime(), name, dumpdir)
                os.unlink(linkpath)
                continue

            dumpdir = os.path.normpath(dumpdir)
            if not dumpdir.startswith(self.config.minidump_storage_path):
                print "[%s] Found record '%s' which points to '%s' outside the minidump storage path" % (time.asctime(), name, dumpdir)
                os.unlink(linkpath)
                continue

            try:
                self.process(dumpdir)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print "[%s] Error while processing dump '%s'. Skipping.: %s" % (time.asctime(), dumpdir, e)
                traceback.print_exc(6)
                continue

            os.unlink(linkpath)

    def loop(self):
        lasttime = 0
        while True:
            if time.time() < lasttime + self.config.processor_wakeinterval:
                time.sleep(lasttime + self.config.processor_wakeinterval - time.time())
            lasttime = time.time()
            try:
                self.searchandprocess()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print "[%s] Continuing after exception: %s" % (time.asctime(), e)

if __name__ == '__main__':
    from config import getconfig
    Processor(getconfig()).loop()
