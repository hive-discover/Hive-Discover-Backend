import cProfile, pstats, io

from multi_agents import MP_ChainListener

from beem import Hive 
from beem.nodelist import NodeList
from beem.blockchain import Blockchain

from multiprocessing import Process, Event, Queue
from threading import Thread

import time

def profile(fnc):   
    """A decorator that uses cProfile to profile a function"""  
    def inner(*args, **kwargs):
        
        pr = cProfile.Profile()
        pr.enable()
        retval = fnc(*args, **kwargs)
        pr.disable()
        s = io.StringIO()
        sortby = 'cumulative'
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        ps.print_stats()
        print(s.getvalue())
        return retval

    return inner


stopping = Event()
listener = MP_ChainListener(stopping)
listener.mp_init()

instance = Hive(node=NodeList().get_nodes(hive=True))
chain = Blockchain(blockchain_instance=instance)
current_num = chain.get_current_block_num()


def do(block):   
    listener.process_block(block)

for block in chain.blocks(start=current_num, stop=(current_num)):          
    do(block)
    break







