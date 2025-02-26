import discord
from discord.ext import commands
import config
import pymongo
import docker
import os
import logging
import datetime

mongo = pymongo.MongoClient(os.environ.get('DOCKORD_MONGO'))
db = mongo['prod']
users = db['users']

docker_client = docker.from_env()


def gen_embed(ctx, output, title=None, img=None):
	embed = discord.Embed(
		color=config.MAINCOLOR,
		description=f"```\n{output}```"
	)
	if title is not None:
		embed.set_author(name=title, icon_url=img)
	return embed


class Session():
	def __init__(self, id: str = None):
		r = users.find_one({'id': id})
		if r is None:
			r = {
				"id": id,
				"container": None,
				"last_command": datetime.datetime.utcnow()
			}
			users.insert_one(r)
		for key, value in r.items():
			setattr(self, key, value)
		if self.container is not None:
			try:
				self.container = docker_client.containers.get(self.container)
			except docker.errors.NotFound:
				self.create_container(id)
				self.refresh()
		else:
			self.create_container(id)
			self.refresh()

	def refresh(self):
		self.__init__(self.id)

	def update(self, update: dict, refresh: bool = True):
		r = users.update_one({'id': self.id}, update)
		if refresh:
			self.refresh()
		return r

	def delete(self):
		self.container.remove(force=True)
		return users.delete_one({'id': self.id})

	def send_command(self, command: str):
		if self.container.status != "running":
			self.container.start()
		# TODO: add timeouts or non-blocking functionality
		exit_code, output = self.container.exec_run(
			f"/bin/sh -c {repr(command)}", tty=True)
		return exit_code, output

	def create_container(self, name):
		if self.container is not None and type(self.container) is docker.models.containers.Container:
			self.container.remove(force=True)
		if not any(["dockord/alpine" in x.tags[0] for x in docker_client.images.list()]):
			logging.info("Fetching docker image 'dockord/alpine'.")
			docker_client.images.pull("dockord/alpine")
			logging.info("Finished fetching 'dockord/alpine'.")
		self.container = docker_client.containers.create(
			'dockord/alpine',
			detach=True,
			mem_limit="32m",
			name=name,
			tty=True
		)
		self.last_command = datetime.datetime.utcnow()
		self.update({'$set': {'container': self.container.id,
                        'last_command': self.last_command}}, False)
		return True
