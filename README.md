# Cloud/DevOps Technical Test - Result

This is a walkthrough of what has been done to meet the requirements of this exercice. We can consider this as a readme as following these instruction will give a working example. But this is also a place used to discuss what is not optimal and what can be imagine to go further.

## Deploying to kubernetes

The goal here is to deploy a Python API to kubernetes. So first we need to build a docker image.

### Prerequisite - Building a docker image for fastapi (Python framework)

We aim at keeping the docker file as simple as possible for multiple reasons.

* Security: we need to be able to quickly understand each line of the Dockerfile in order to be sure what will contain the image we will deploy
* No configuration built-in in the image. For a deployment in kubernetes we will need to be able to manage configuration dynamically, for example to reach the right mongodb database for the current environment

We will discuss this matter a bit more later so we'll stop here for now.
Here is the Dockerfile we will use in this exercise

```
FROM python:3.7

RUN pip install fastapi uvicorn python-dotenv pymongo

COPY ./app /app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
```

We start with a python base image (we will discuss this later). We install the depencies we need and that are not included in the base image.

We copy the app folder containing the fastapi code in the container. We can notice here that we don't copy the .env file in this docker image. We'll get back to that later. 
* Note: we modified the app/\_\_init__.py file provided by modifying the env_file variable from .env to config/.env - more on this later (the change have been reflected in this repository)

We then use CMD to launch our application at container startup.

For the purpose of this exercise we will publish this image using dockerhub. 

We first create a directory containing this Docker file and the app folder (we can obtain such directory by cloning this git repository). Then we use the following commands:
```
docker build -t gmiamz/untienots:0.4 . // Create the docker image locally and tag it
docker push gmiamz/untienots:0.4 // push the docker image to the dockerhub repository
```

### Prerequisite - Build your own kubernetes cluster

In our case we need to have a kubernetes cluster, but we don't need it to be production ready (yet). So we use the k3s distribution which allow to build very quickly a kubernetes cluster and providing by default an Traefik based ingress.

* Traefik is a reverse proxy which can natively be used as kubernetes ingress
* Kubernetes ingress is the object which is used to expose HTTP(s) endpoint for clients outside our cluster.

Installation is very very simple:

```
curl -sfL https://get.k3s.io | sh -
```
Note that piping the result of a curl directly in a shell is strongly not recommended (see [for example](https://www.idontplaydarts.com/2016/04/detecting-curl-pipe-bash-server-side/))

And... that's it!

### Prerequisite - Install mongodb in kubernetes

For the purpose of this exercise we want to install mongodb directly inside our kubernetes cluster. While this may be very challenging to do in production it actually makes sense to be able to have a self contained environment for development needs.

We will use the [community mongodb operator](https://github.com/mongodb/mongodb-kubernetes-operator.git) to do this. This will install an operator in charge of maintaining the statefulset which will provide the mongod themselves (3 by default) but will also provide capabilities to create users and assign roles and permissions to them.

All the files we will use in order to create this mongodb cluster + operator and any other related resources are located in the mongodb folder of this git repository. All the values used in this example are harcoded in those files. But we will highlight here what we did that is not explicitly in the official documentation of the operator.

```
kubectl create ns mongodb // we create a dedicated namespace for the database
// we create the custom resource definitions used by the operator
kubectl apply -f mongodb/mongodbcommunity.mongodb.com_mongodbcommunity.yaml 
// we create all the roles and permissions fot the custom resources
kubectl apply -f mongodb/role.yaml -n mongodb
kubectl apply -f mongodb/role_binding.yaml -n mongodb  
kubectl apply -f mongodb/service_account.yaml -n mongodb  
// deployment for the mongo operator itself
kubectl create -f mongodb/manager.yaml -n mongodb
// We create the user we will use with its password and roles/permissions
kubectl apply -f mongodb/mongodb.com_v1_mongodbcommunity_cr.yaml -n mongodb  (user, role and password)
```

* Note: For this last file, the password is hardcoded in it (it is possible to delete the secret once the user is created), and we add a role readWriteAnyDatabase on the default db admin. We recommend to check the detail of this file for a better understanding. This is not optimal on a security standpoint, but rbac fine tuning has been considered out of scope of this exercise

After this we should have an operator pod up and running alongside three mongodb pods managed by a statefulset.

### Deploy our API in our cluster

First we create a configmap based on the .env file provided. This will be used to mount the config file as a volume/file inside the container of our applicative pod.

We can notice that the mongodb url is now: mongodb://admin:my-secure-password@example-mongodb-svc.mongodb.svc.cluster.local:27017/?replicaSet=example-mongodb

This reflect our new mongodb deployement:
* admin is the user we created
* my-secure-password is the password we associated with this user
* example-mongodb-svc is the name of the kubernetes service created for the database
* mongodb is the name of the namespace in which we deployed our database
* .svc.cluster.local is the domain of the kubernetes network, this is mandatory for the DNS resolution inside the cluster
* 27017 is the default mongodb port and we keep it as is
* The last part is the default replicaSet (mongodb meaning, not kube) created by the operator

```
kubectl -n untienots create configmap dotenv --from-file=.env
```

We then create our deployment (which will manage our applicative pod) and an associated service to make the pod easily reachable for other services deployed in the cluster.

Here is the file used to define those objects:
```
apiVersion: apps/v1
kind: Deployment
metadata:
  name: untienots
  labels:
    app: untienots
spec:
  replicas: 1
  selector:
    matchLabels:
      app: untienots
  template:
    metadata:
      labels:
        app: untienots
    spec:
      containers:
      - args:
        name: untienots
        image: gmiamz/untienots:0.4 // The docker image we retrieve from dockerhub
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 80
          name: http-api
          protocol: TCP
        volumeMounts: // we mount the file .env in /config/ based on the volume dot env below 
        - mountPath: /config 
          name: dotenv
          readOnly: true
      volumes:  // We define the volume based on the configmap we created
      - configMap:
          name: dotenv
        name: dotenv
---
apiVersion: v1
kind: Service
metadata:
  name: untienots-svc
spec:
  ports:
  - name: http
    port: 80
    protocol: TCP
    targetPort: 80
  selector:
    app: untienots
  sessionAffinity: None
  type: ClusterIP
```

Based on this file, we can deploy.
```
kubectl -n untienots apply -f kube/untienots.yaml
```

It's now time to check that everything is working as intended

```
root@ip-172-31-1-66:/home/ubuntu# kubectl -n untienots get svc
NAME            TYPE        CLUSTER-IP    EXTERNAL-IP   PORT(S)   AGE
untienots-svc   ClusterIP   10.43.18.32   <none>        80/TCP    8s
// We will use the cluster-ip of the service to call the API from the host server
root@ip-172-31-1-66:~# curl -L http://10.43.18.32/users
[]
root@ip-172-31-1-66:~# curl -L -X POST http://10.43.18.32/users -d '{"name": "test-name", "username": "test-username", "email" : "username@email.com"}'
root@ip-172-31-1-66:~# curl -L http://10.43.18.32/users
[{"_id":"608807ffaccf71c7ca4c9791","name":"test-name","username":"test-username","email":"username@email.com"}]
```

It works!

We were able to check that there was no users in the database. We were then able to create a user and to retrieve it and all of this using only the API.

* Note: at this point, everything is full HTTP, no encryption. This is not necessarily a problem yet as we don't expose anything over internet. Also this is not always an anti-pattern regarding kubernetes deployments as we can use a service mesh (istio/linkerd/...) to add a sidecar to the pod. This deployment pattern let the applicative container expose HTTP while the pod will expose HTTPS only. This also let the developpers to not have to handle anything related to encryption and in the same time this allow us to be 100% sure that everything is HTTPS. More on this later.


