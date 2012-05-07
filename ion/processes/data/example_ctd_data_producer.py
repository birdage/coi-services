# New Stream and Granule Stuff....

#@todo - move this to: ion.processes.data.example_ctd_data_producer

'''
To Run:
bin/pycc --rel res/deploy/r2dm.yml
### In the shell...

# create a stream id and pass it in...
from interface.services.dm.ipubsub_management_service import PubsubManagementServiceClient
pmsc = PubsubManagementServiceClient(node=cc.node)
stream_id = pmsc.create_stream(name='pfoo')
pid = cc.spawn_process(name='ctd_test',module='ion.processes.data.ctd_stream_publisher',cls='NewGranuleCTDPublisher',config={'process':{'stream_id':stream_id}})


'''


### Taxonomies are defined before hand out of band... somehow.
tx = TaxyCab()
tx.add_taxonomy_set('temp','long name for temp')
tx.add_taxonomy_set('cond','long name for cond')
tx.add_taxonomy_set('lat','long name for latitude')
tx.add_taxonomy_set('lon','long name for longitude')
tx.add_taxonomy_set('pres','long name for pres')
tx.add_taxonomy_set('time','long name for time')
# This is an example of using groups it is not a normative statement about how to use groups
tx.add_taxonomy_set('group1','This group contains coordinates...')
tx.add_taxonomy_set('group0','This group contains data...')

class NewGranuleCTDPublisher(SimpleCtdPublisher):

    #@todo Change name to ExampleCTDDataProducer

    #overriding trigger function here to use new granule
    def _trigger_func(self, stream_id):

        #@todo - add lots of comments in here
        while True:

            length = 10

            c = [random.uniform(0.0,75.0)  for i in xrange(length)]

            t = [random.uniform(-1.7, 21.0) for i in xrange(length)]

            p = [random.lognormvariate(1,2) for i in xrange(length)]

            lat = [random.uniform(-90.0, 90.0) for i in xrange(length)]

            lon = [random.uniform(0.0, 360.0) for i in xrange(length)]

            tvar = [self.last_time + i for i in xrange(1,length+1)]

            self.last_time = max(tvar)

            rdt = RecordDictionaryTool(taxonomy=tx)

            # This is an example of using groups it is not a normative statement about how to use groups

            rdt0 = RecordDictionaryTool(taxonomy=tx)

            #@todo - add a value sequence of raw bytes - not sure the type below is correct?
            #rdt[raw] = numpy.ndarray(['Raw stuff',], dtype='bytes')

            rdt0['temp'] = t
            rdt0['cond'] = c
            rdt0['pres'] = p

            rdt1 = RecordDictionaryTool(taxonomy=tx)

            rdt1['time'] = tvar
            rdt1['lat'] = lat
            rdt1['lon'] = lon

            rdt['group1'] = rdt1
            rdt['group0'] = rdt0

            g = build_granule(data_producer_id='Bobs Potatoes', taxonomy=tx, record_dictionary=rdt)

            log.info('%s sending %d values!' % (self.__class__.__name__, length))
            self.publisher.publish(g)

            time.sleep(2.0)