from __future__ import print_function
import tensorflow as tf
import argparse
import tensorflow.examples.tutorials.mnist.input_data as input_data
import time
from keras.datasets import mnist
FLAGS = None
REPLICAS_TO_AGGREGATE = 2
X = tf.placeholder("float", shape = [None,num_inputs])

batch_size = 64
num_steps = 40000
learning_rate = 5e-1
display_step = 1000

num_inputs = 784
num_h1 = 256
num_h2 = 128

def encoder_layer(x):
    l1 = tf.matmul(x, W["w1"])
    l1 = tf.add(l1,b["b1"])
    l1 = tf.nn.sigmoid(l1)

    l1 = tf.matmul(l1, W["w2"])
    l1 = tf.add(l1,b["b2"])
    l1 = tf.nn.sigmoid(l1)

    return l1

def decoder_layer(x):
    l2 = tf.matmul(x, W["w3"])
    l2 = tf.add(l2,b["b3"])
    l2 = tf.nn.sigmoid(l2)

    l2 = tf.matmul(l2, W["w4"])
    l2 = tf.add(l2,b["b4"])
    l2 = tf.nn.sigmoid(l2)

    return l2

#defining the weight matrices
W = {"w1" : tf.Variable(tf.random_normal([num_inputs, num_h1])),
     "w2" : tf.Variable(tf.random_normal([num_h1,num_h2])),
     "w3" : tf.Variable(tf.random_normal([num_h2,num_h1])),
     "w4" : tf.Variable(tf.random_normal([num_h1, num_inputs]))}

b = { "b1" : tf.Variable(tf.random_normal([num_h1])),
      "b2" : tf.Variable(tf.random_normal([num_h2])),
      "b3" : tf.Variable(tf.random_normal([num_h1])),
      "b4" : tf.Variable(tf.random_normal([num_inputs]))} 

encoder_fun = encoder_layer(X)
decoder_fun = decoder_layer(encoder_fun)

prediction = decoder_fun
actual = X

cost_fun = tf.reduce_mean(tf.pow(actual - prediction, 2))
optim = tf.train.GradientDescentOptimizer(learning_rate)
train_step = optim.minimize(cost_fun)

def main():
  # Configure
  config=tf.ConfigProto(log_device_placement=False)

  # Server Setup
  cluster = tf.train.ClusterSpec({
        'ps':['localhost:2222'],
        'worker':['localhost:2223','localhost:2224']
        }) #allows this node know about all other nodes
  if FLAGS.job_name == 'ps': #checks if parameter server
    server = tf.train.Server(cluster,
          job_name="ps",
          task_index=FLAGS.task_index,
          config=config)
    server.join()
  else: #it must be a worker server
    is_chief = (FLAGS.task_index == 0) #checks if this is the chief node
    server = tf.train.Server(cluster,
          job_name="worker",
          task_index=FLAGS.task_index,
          config=config)
    
    # Graph
    worker_device = "/job:%s/task:%d/cpu:0" % (FLAGS.job_name,FLAGS.task_index)
    with tf.device(tf.train.replica_device_setter(ps_tasks=1,
          worker_device=worker_device)):

      a = tf.Variable(tf.constant(0.,shape=[2]),dtype=tf.float32)
      b = tf.Variable(tf.constant(0.,shape=[2]),dtype=tf.float32)
      c=a+b

      global_step = tf.Variable(0,dtype=tf.int32,trainable=False,name='global_step')
      target = tf.constant(100.,shape=[2],dtype=tf.float32)
      loss = tf.reduce_mean(tf.square(c-target))

      # create an optimizer then wrap it with SynceReplicasOptimizer
      optimizer = tf.train.GradientDescentOptimizer(.0001)
      optimizer1 = tf.train.SyncReplicasOptimizer(optimizer,
            replicas_to_aggregate=REPLICAS_TO_AGGREGATE, total_num_replicas=2)
      
      opt = optimizer1.minimize(loss,global_step=global_step) # averages gradients
      #opt = optimizer1.minimize(REPLICAS_TO_AGGREGATE*loss,
      #                           global_step=global_step) # hackily sums gradients

    # Session
    sync_replicas_hook = optimizer1.make_session_run_hook(is_chief)
    stop_hook = tf.train.StopAtStepHook(last_step=10)
    hooks = [sync_replicas_hook,stop_hook]

    # Monitored Training Session
    sess = tf.train.MonitoredTrainingSession(master = server.target, 
          is_chief=is_chief,
          config=config,
          hooks=hooks,
          stop_grace_period_secs=10)

    print('Starting training on worker %d'%FLAGS.task_index)
    while not sess.should_stop():
      _,r,gs=sess.run([opt,c,global_step])
      print(r,'step: ',gs,'worker: ',FLAGS.task_index)
      if is_chief: time.sleep(1)
      time.sleep(1)
    print('Done',FLAGS.task_index)

    time.sleep(10) #grace period to wait before closing session
    sess.close()
    print('Session from worker %d closed cleanly'%FLAGS.task_index)


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  # Flags for defining the tf.train.ClusterSpec
  parser.add_argument(
      "--job_name",
      type=str,
      default="",
      help="One of 'ps', 'worker'"
    )
  # Flags for defining the tf.train.Server
  parser.add_argument(
      "--task_index",
      type=int,
      default=0,
      help="Index of task within the job"
    )
  FLAGS, unparsed = parser.parse_known_args()
  print(FLAGS.task_index)
  main()